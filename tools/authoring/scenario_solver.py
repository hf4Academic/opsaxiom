"""
场景自动求解器（H-gen 核心杠杆）——给一个 Skill 反推出走到 done 的 context_walk 场景。

思路：从 entry 前向走树。到 check 节点时，为它的某个通向"能到 done"的分支，
按 when 表达式合成满足它的 node_ctx；用真实 exprlang 验证分支确实为真。
到 ask 节点选第一个通向 done 的 option。走到 done 即成功，产出可被 run_sim 验证的场景。

合成靠启发式覆盖 exprlang 常见形态（比较/count/any/all/matches/and/or/not）。
合成不出就返回 None（该 Skill 需人工场景）——诚实，不硬造。

关键纪律：产出的场景必须 run_sim 实跑 path_ok=True 才算数（调用方负责跑一遍）。
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import exprlang  # noqa: E402


def _reaches_done(nodes, start, seen=None):
    """从 start 能否到达 done 节点（BFS）。"""
    seen = seen or set()
    stack = [start]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        n = nodes.get(nid)
        if nid == "done" or (n and n.get("type") == "done"):
            return True
        if n is None:
            continue
        for br in n.get("branch", []) or []:
            stack.append(br.get("goto"))
        if n.get("otherwise"):
            stack.append(n["otherwise"])
        for o in n.get("options", []) or []:
            stack.append(o.get("goto"))
        if n.get("goto"):
            stack.append(n["goto"])
    return False


def _set(ctx, root, sub, value):
    """把 root[.sub] 写进 ctx（sub 为 None → 顶层标量；否则 rows[0].sub / output.sub）。"""
    if sub is None:
        ctx[root] = value
        ctx.setdefault("output", {})[root] = value
    elif root == "rows":
        ctx.setdefault("rows", [{}])
        if not ctx["rows"]:
            ctx["rows"] = [{}]
        ctx["rows"][0][sub] = value
    elif root == "output":
        ctx.setdefault("output", {})[sub] = value
    else:
        ctx.setdefault(root, {})
        if isinstance(ctx[root], dict):
            ctx[root][sub] = value


_CMP = re.compile(r"([A-Za-z_][\w\.\[\]]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)")


def _sample_matching(pat):
    """给一个能被正则 pat（search 语义）匹配的样例字符串。覆盖常见形态。"""
    alt = pat.split("|")[0]                       # 取第一个候选
    s = alt
    s = re.sub(r"\[0-9\]\+|\\d\+|\[0-9\]\*|\d\+", "5", s)
    s = re.sub(r"\[\^?[^\]]*\]\+?", "x", s)        # 其它字符类 → x
    s = s.replace(".*", "x").replace(".+", "x").replace(".", "x")
    s = s.replace("\\", "").strip("^$()")
    try:
        return s if re.search(pat, s) else (alt.strip("^$") + " 5 seconds")
    except re.error:
        return alt.strip("^$")


def _synth_for_branch(when, base):
    """为单个 when 表达式合成 ctx（在 base 上叠加）。返回 ctx。
    覆盖：数值比较、count(...)、any/all(FIELD[] matches 'pat')、not any(...)、
    裸布尔字段、matches。and 组合天然被逐子句覆盖。"""
    ctx = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    ctx.setdefault("rows", [{}])
    ctx.setdefault("output", {})

    # not any(FIELD[] matches 'pat') → 该列表为空（any 为假）
    for m in re.finditer(r"not\s+(?:any|all)\(\s*(\w+)\[\]\s+matches", when):
        ctx[m.group(1)] = []

    # any/all(FIELD[] matches 'pat') （非 not 前缀）→ 列表含匹配串
    for m in re.finditer(r"(?<!not )(?:any|all)\(\s*(\w+)\[\]\s+matches\s*['\"]([^'\"]+)['\"]", when):
        field, pat = m.group(1), m.group(2)
        if field == "rows":
            continue
        ctx[field] = [_sample_matching(pat)]

    # any/all(FIELD[].sub OP num) → 列表含满足的对象行；not any(...) → 空列表
    for m in re.finditer(r"(not\s+)?(?:any|all)\(\s*(\w+)\[\]\.(\w+)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)", when):
        neg, field, sub, op, num = m.groups()
        num = float(num); num = int(num) if num == int(num) else num
        if neg:
            ctx[field] = []
        else:
            val = {">=": num, ">": num + 1, "<=": num, "<": num - 1,
                   "==": num, "!=": num + 1}[op]
            ctx[field] = [{sub: val}]

    # count(rows[]... matches ... / rows) OP N → 给足行数（含 matches 行内容）
    for m in re.finditer(r"count\(([^)]*)\)\s*(>=|>|==|<=|<)\s*(\d+)", when):
        n = int(m.group(3)); op = m.group(2)
        need = {">=": n, ">": n + 1, "==": n, "<=": max(n, 1), "<": max(n - 1, 1)}[op]
        inner = m.group(1)
        pm = re.search(r"matches\s*['\"]([^'\"]+)['\"]", inner)
        rowfield = re.search(r"rows\[\]\.(\w+)", inner)
        row = {}
        if pm and rowfield:
            row[rowfield.group(1)] = _sample_matching(pm.group(1))
        ctx["rows"] = [dict(row) for _ in range(max(need, 1))]

    # 字符串等值：field == 'str' / field != 'str'
    for m in re.finditer(r"([A-Za-z_][\w\.\[\]]*)\s*(==|!=)\s*['\"]([^'\"]+)['\"]", when):
        ref, op, s = m.group(1), m.group(2), m.group(3)
        val = s if op == "==" else s + "_other"
        for root, sub in exprlang.field_refs(ref):
            _set(ctx, root, sub, val)
            break

    # 数值比较：field OP num
    for m in _CMP.finditer(when):
        ref, op, num = m.group(1), m.group(2), float(m.group(3))
        num = int(num) if num == int(num) else num
        val = {">=": num, ">": num + 1, "<=": num, "<": num - 1,
               "==": num, "!=": num + 1}[op]
        for root, sub in exprlang.field_refs(ref):
            _set(ctx, root, sub, val)
            break

    # field matches 'str'（裸字段，非 count/any 内）→ 匹配串
    for m in re.finditer(r"(?<![(\.])\b([a-z_]\w*(?:\.\w+)?(?:\[0\]\.\w+)?)\s+matches\s*['\"]([^'\"]+)['\"]", when):
        ref = m.group(1)
        if ref in ("any", "all", "count"):
            continue
        for root, sub in exprlang.field_refs(ref):
            _set(ctx, root, sub, _sample_matching(m.group(2)))
            break

    # 裸布尔字段 → True（未被上面覆盖的字段引用，且不在 not 后）
    negated = set(re.findall(r"not\s+([a-z_]\w*)", when))
    for root, sub in exprlang.field_refs(when):
        if root in ("count", "any", "all", "max", "min", "avg", "sum", "delta", "lines"):
            continue
        cur = ctx.get(root)
        already = (sub is None and root in ctx) or \
                  (sub and isinstance(cur, dict) and sub in cur) or \
                  (root == "rows" and ctx["rows"] and sub in ctx["rows"][0]) or \
                  (root == "output" and sub in ctx["output"])
        if not already:
            _set(ctx, root, sub, root not in negated)
    return ctx


def _eval_branch(node, ctx):
    """返回该 ctx 下 check 走向的 goto（复用 run_sim 语义）。"""
    for br in node.get("branch", []) or []:
        try:
            if exprlang._truthy(exprlang.evaluate(br["when"], ctx)):
                return br["goto"]
        except exprlang.EvalError:
            pass
    return node.get("otherwise")


def solve(skill, base_ctx=None, max_steps=40):
    """返回 (node_ctx, answers, path) 或 None。node_ctx 使各 check 走向 done。"""
    nodes = {n["id"]: n for n in skill["tree"]["nodes"]}
    node = skill["tree"]["entry"]
    node_ctx, answers, path = {}, {}, [node]
    base = dict(base_ctx or {})
    steps = 0
    while steps < max_steps:
        steps += 1
        n = nodes.get(node)
        if n is None:                          # 裸 token
            return (node_ctx, answers, path) if node == "done" else None
        t = n["type"]
        if t == "done":
            return node_ctx, answers, path
        if t == "escalate":
            return None                        # 只求解到 done 的成功路径
        if t == "ask":
            opt = next((o for o in n.get("options", [])
                        if _reaches_done(nodes, o.get("goto"))), None)
            if not opt:
                return None
            answers[node] = opt["goto"]
            node = opt["goto"]; path.append(node); continue
        if t == "action":
            node = n.get("goto") or "escalate"
            path.append(node); continue
        if t == "check":
            # 选一个既能满足、又能通向 done 的分支
            picked = None
            for br in n.get("branch", []) or []:
                if not _reaches_done(nodes, br.get("goto")):
                    continue
                ctx = _synth_for_branch(br["when"], base)
                if _eval_branch(n, ctx) == br["goto"]:
                    picked = (br["goto"], ctx); break
            if not picked:
                return None
            goto, ctx = picked
            # 只留该节点相关字段进 node_ctx（output + rows）
            nc = {}
            if ctx.get("output"):
                nc["output"] = ctx["output"]
            if ctx.get("rows"):
                nc["rows"] = ctx["rows"]
            for k, v in ctx.items():
                if k not in ("output", "rows") and not isinstance(v, dict):
                    nc[k] = v
            node_ctx[node] = nc
            node = goto; path.append(node); continue
        return None
    return None
