"""
受限表达式语言（docs/03 §5，规则 S5）—— 保守子集，fail-closed。

只允许：字段引用、数值/字符串比较、and/or/not、聚合函数 max/min/count/any/all、
增量函数 delta、matches 运算符、时长字面量（如 60s）、括号、四则运算（仅用于阈值系数）。
其余一律解析失败 → 判定非法（宁可严不可松）。

对外接口：validate_when(expr:str) -> (ok:bool, error:str|None)

实现方式：自研 tokenizer + 递归下降 parser，不依赖外部语法库，行为完全可控。
"""
import re

# 保留字与函数名
_KEYWORDS = {"and", "or", "not", "matches"}
_FUNCS = {"max", "min", "count", "any", "all", "delta", "avg", "sum"}

# token 规则（顺序敏感：DURATION 必须在 NUMBER 之前）
_TOKEN_SPEC = [
    ("WS",       r"[ \t\r\n]+"),
    ("DURATION", r"[0-9]+[smh](?![a-zA-Z0-9_])"),
    ("NUMBER",   r"[0-9]+(?:\.[0-9]+)?"),
    ("STRING",   r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\""),
    ("OP2",      r"==|!=|>=|<="),
    ("OP1",      r"[><+\-*/().,\[\]]"),
    ("NAME",     r"[A-Za-z_][A-Za-z0-9_]*"),
]
_MASTER = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _TOKEN_SPEC))


class _Tok:
    __slots__ = ("kind", "val", "pos")

    def __init__(self, kind, val, pos):
        self.kind, self.val, self.pos = kind, val, pos

    def __repr__(self):
        return f"{self.kind}({self.val!r})"


class ExprError(Exception):
    pass


def _tokenize(s):
    toks, i = [], 0
    while i < len(s):
        m = _MASTER.match(s, i)
        if not m:
            raise ExprError(f"非法字符 @{i}: {s[i:i+10]!r}")
        i = m.end()
        kind = m.lastgroup
        if kind == "WS":
            continue
        val = m.group()
        if kind == "NAME" and val in _KEYWORDS:
            kind = "KW"
        toks.append(_Tok(kind, val, m.start()))
    toks.append(_Tok("EOF", "", len(s)))
    return toks


class _Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    @property
    def cur(self):
        return self.toks[self.i]

    def eat(self, kind=None, val=None):
        t = self.cur
        if kind and t.kind != kind:
            raise ExprError(f"期望 {kind}，得到 {t}")
        if val and t.val != val:
            raise ExprError(f"期望 {val!r}，得到 {t.val!r}")
        self.i += 1
        return t

    # ---- 文法（低→高优先级）----
    def parse(self):
        node = self.p_or()
        if self.cur.kind != "EOF":
            raise ExprError(f"多余 token: {self.cur}")
        return node

    def p_or(self):
        self.p_and()
        while self.cur.kind == "KW" and self.cur.val == "or":
            self.eat(); self.p_and()

    def p_and(self):
        self.p_not()
        while self.cur.kind == "KW" and self.cur.val == "and":
            self.eat(); self.p_not()

    def p_not(self):
        if self.cur.kind == "KW" and self.cur.val == "not":
            self.eat(); self.p_not()
        else:
            self.p_cmp()

    def p_cmp(self):
        self.p_add()
        if self.cur.kind == "OP2" or (self.cur.kind == "OP1" and self.cur.val in "><"):
            self.eat(); self.p_add()
        elif self.cur.kind == "KW" and self.cur.val == "matches":
            self.eat(); self.eat("STRING")

    def p_add(self):
        self.p_mul()
        while self.cur.kind == "OP1" and self.cur.val in "+-":
            self.eat(); self.p_mul()

    def p_mul(self):
        self.p_unary()
        while self.cur.kind == "OP1" and self.cur.val in "*/":
            self.eat(); self.p_unary()

    def p_unary(self):
        if self.cur.kind == "OP1" and self.cur.val == "-":
            self.eat(); self.p_unary()
        else:
            self.p_atom()

    def p_atom(self):
        t = self.cur
        if t.kind in ("NUMBER", "DURATION", "STRING"):
            self.eat(); return
        if t.kind == "OP1" and t.val == "(":
            self.eat("OP1", "("); self.p_or(); self.eat("OP1", ")"); return
        if t.kind == "NAME":
            self.eat()
            # 函数调用？
            if self.cur.kind == "OP1" and self.cur.val == "(":
                if t.val not in _FUNCS:
                    raise ExprError(f"未知函数 {t.val!r}（仅允许 {sorted(_FUNCS)}）")
                self.eat("OP1", "(")
                if not (self.cur.kind == "OP1" and self.cur.val == ")"):
                    self.p_or()
                    while self.cur.kind == "OP1" and self.cur.val == ",":
                        self.eat(); self.p_or()
                self.eat("OP1", ")")
                return
            # 否则是字段引用，消费访问器链
            self._accessors()
            return
        raise ExprError(f"意外 token: {t}")

    def _accessors(self):
        while True:
            if self.cur.kind == "OP1" and self.cur.val == ".":
                self.eat(); self.eat("NAME")
            elif self.cur.kind == "OP1" and self.cur.val == "[":
                self.eat("OP1", "[")
                if self.cur.kind == "NUMBER":      # rows[0]
                    self.eat("NUMBER")
                # else rows[]  —— 数组投影，中括号内为空
                self.eat("OP1", "]")
            else:
                break


def validate_when(expr):
    """返回 (ok, error)。ok=True 表示表达式合法。"""
    if not isinstance(expr, str) or not expr.strip():
        return False, "空表达式"
    try:
        _Parser(_tokenize(expr)).parse()
        return True, None
    except ExprError as e:
        return False, str(e)


# ============================================================================
# 求值器（Evaluator）—— 运行时引擎核心，供仿真执行器(O-6)与未来运行时使用。
# 与验证器共用 tokenizer；这里是第二遍递归下降，返回实际值。
# 语义：标量比较返回 bool；列表 vs 标量的比较/matches 逐元素返回 bool 列表；
# count(列表)=真值元素个数，max/min 取数值极值，any/all 对布尔列表求逻辑。
# ============================================================================
class EvalError(Exception):
    pass


def _truthy(v):
    return bool(v) and v is not None


def _cmp(op, a, b):
    import operator
    fn = {"==": operator.eq, "!=": operator.ne, ">": operator.gt,
          "<": operator.lt, ">=": operator.ge, "<=": operator.le}[op]

    def one(x, y):
        if x is None or y is None:
            return False
        try:
            return fn(x, y)
        except TypeError:
            return fn(str(x), str(y))
    if isinstance(a, list):
        return [one(x, b) for x in a]
    return one(a, b)


class _Eval:
    def __init__(self, toks, ctx):
        self.toks, self.i, self.ctx = toks, 0, ctx

    @property
    def cur(self):
        return self.toks[self.i]

    def eat(self, kind=None, val=None):
        t = self.cur
        if kind and t.kind != kind:
            raise EvalError(f"期望 {kind}，得到 {t}")
        if val and t.val != val:
            raise EvalError(f"期望 {val!r}，得到 {t.val!r}")
        self.i += 1
        return t

    def run(self):
        v = self.e_or()
        if self.cur.kind != "EOF":
            raise EvalError(f"多余 token: {self.cur}")
        return v

    def e_or(self):
        v = self.e_and()
        while self.cur.kind == "KW" and self.cur.val == "or":
            self.eat(); v = _truthy(v) or _truthy(self.e_and())
        return v

    def e_and(self):
        v = self.e_not()
        while self.cur.kind == "KW" and self.cur.val == "and":
            self.eat(); r = self.e_not(); v = _truthy(v) and _truthy(r)
        return v

    def e_not(self):
        if self.cur.kind == "KW" and self.cur.val == "not":
            self.eat(); return not _truthy(self.e_not())
        return self.e_cmp()

    def e_cmp(self):
        v = self.e_add()
        if self.cur.kind == "OP2" or (self.cur.kind == "OP1" and self.cur.val in "><"):
            op = self.eat().val
            return _cmp(op, v, self.e_add())
        if self.cur.kind == "KW" and self.cur.val == "matches":
            self.eat()
            pat = self.eat("STRING").val[1:-1]
            rx = re.compile(pat)
            if isinstance(v, list):
                return [bool(rx.search(str(x))) for x in v if x is not None]
            return bool(rx.search(str(v)))
        return v

    def e_add(self):
        v = self.e_mul()
        while self.cur.kind == "OP1" and self.cur.val in "+-":
            op = self.eat().val
            r = self.e_mul()
            if isinstance(v, list) and isinstance(r, list):
                v = [(a or 0) + (b or 0) if op == "+" else (a or 0) - (b or 0)
                     for a, b in zip(v, r)]
            else:
                v = (v or 0) + (r or 0) if op == "+" else (v or 0) - (r or 0)
        return v

    def e_mul(self):
        v = self.e_unary()
        while self.cur.kind == "OP1" and self.cur.val in "*/":
            op = self.eat().val
            r = self.e_unary()
            v = (v or 0) * (r or 0) if op == "*" else (v or 0) / (r or 1)
        return v

    def e_unary(self):
        if self.cur.kind == "OP1" and self.cur.val == "-":
            self.eat(); return -(self.e_unary() or 0)
        return self.e_atom()

    def e_atom(self):
        t = self.cur
        if t.kind == "NUMBER":
            self.eat(); return float(t.val) if "." in t.val else int(t.val)
        if t.kind == "DURATION":
            self.eat(); return int(t.val[:-1])   # 秒/分/时的数值部分，sim 里按同单位处理
        if t.kind == "STRING":
            self.eat(); return t.val[1:-1]
        if t.kind == "OP1" and t.val == "(":
            self.eat(); v = self.e_or(); self.eat("OP1", ")"); return v
        if t.kind == "NAME":
            self.eat()
            if self.cur.kind == "OP1" and self.cur.val == "(":
                return self._func(t.val)
            return self._fieldref(t.val)
        raise EvalError(f"意外 token: {t}")

    def _func(self, name):
        self.eat("OP1", "(")
        args = [self.e_or()]
        while self.cur.kind == "OP1" and self.cur.val == ",":
            self.eat(); args.append(self.e_or())
        self.eat("OP1", ")")
        x = args[0]
        if name == "count":
            # 布尔元素按 True 计数（来自逐元素比较）；非布尔按"存在"计数(非 None)，
            # 使 count(rows)=行数（即使某行是空 dict），count(rows[].x>k)=满足个数。
            def _cnt1(e):
                if isinstance(e, bool):
                    return 1 if e else 0
                return 1 if e is not None else 0
            return sum(_cnt1(e) for e in x) if isinstance(x, list) else _cnt1(x)
        if name in ("max", "min", "avg", "sum"):
            xs = [e for e in (x if isinstance(x, list) else [x]) if e is not None]
            if not xs:
                return None if name in ("max", "min", "avg") else 0
            if name == "max":
                return max(xs)
            if name == "min":
                return min(xs)
            if name == "sum":
                return sum(xs)
            return sum(xs) / len(xs)   # avg
        if name in ("any", "all"):
            xs = x if isinstance(x, list) else [x]
            return (any if name == "any" else all)(_truthy(e) for e in xs)
        if name == "delta":
            # sim：从 ctx['__delta__'][field] 读预置增量；缺省 0
            key = self._last_field
            return (self.ctx.get("__delta__", {}) or {}).get(key, 0)
        raise EvalError(f"未知函数 {name}")

    def _fieldref(self, name):
        self._last_field = name
        if name not in self.ctx:
            # 未知字段 → None（sim 视为该分支不成立，走 otherwise）
            val = None
        else:
            val = self.ctx[name]
        while True:
            if self.cur.kind == "OP1" and self.cur.val == ".":
                self.eat(); f = self.eat("NAME").val
                self._last_field = f
                if isinstance(val, list):
                    val = [(e.get(f) if isinstance(e, dict) else None) for e in val]
                elif isinstance(val, dict):
                    val = val.get(f)
                else:
                    val = None
            elif self.cur.kind == "OP1" and self.cur.val == "[":
                self.eat("OP1", "[")
                if self.cur.kind == "NUMBER":
                    idx = int(self.eat("NUMBER").val)
                    val = val[idx] if isinstance(val, list) and -len(val) <= idx < len(val) else None
                # else []：投影模式，保持 val 为列表，后续 .field 会逐元素取
                self.eat("OP1", "]")
            else:
                break
        return val


def evaluate(expr, ctx):
    """对表达式求值，ctx 为变量字典。解析/求值出错抛 EvalError。"""
    return _Eval(_tokenize(expr), ctx).run()


def parse_template_ref(s):
    """解析 {{...}} 内部的字段引用（v0.2 §7.4，与 branch.when 同文法的字段引用子集）。
    返回 (ok, root, second)：ok=是否合法字段引用；root=根标识符；
    second=紧随 root 的下一段名字（用于 discovery.<id> 形式），无则 None。
    仅允许 NAME (.NAME | [NUMBER] | [])* ，其余（函数、运算、比较）一律非法。"""
    s = s.strip()
    try:
        toks = _tokenize(s)
    except ExprError:
        return False, None, None
    if not toks or toks[0].kind != "NAME":
        return False, None, None
    root = toks[0].val
    second = None
    i = 1
    # 记录第一个 . 后的名字
    if i < len(toks) and toks[i].kind == "OP1" and toks[i].val == "." \
            and i + 1 < len(toks) and toks[i + 1].kind == "NAME":
        second = toks[i + 1].val
    # 校验剩余 token 仅为访问器
    while i < len(toks) and toks[i].kind != "EOF":
        t = toks[i]
        if t.kind == "OP1" and t.val == ".":
            if i + 1 >= len(toks) or toks[i + 1].kind != "NAME":
                return False, None, None
            i += 2
        elif t.kind == "OP1" and t.val == "[":
            i += 1
            if i < len(toks) and toks[i].kind == "NUMBER":
                i += 1
            if i >= len(toks) or not (toks[i].kind == "OP1" and toks[i].val == "]"):
                return False, None, None
            i += 1
        else:
            return False, None, None
    return True, root, second


if __name__ == "__main__":
    import sys
    for e in sys.argv[1:]:
        print(validate_when(e), "\t", e)
