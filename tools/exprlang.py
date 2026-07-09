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
_FUNCS = {"max", "min", "count", "any", "all", "delta"}

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


if __name__ == "__main__":
    import sys
    for e in sys.argv[1:]:
        print(validate_when(e), "\t", e)
