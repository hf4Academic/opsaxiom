"""通用解析器族（H-0，Fable 金标准实现）——批量扩容到 200 Skill 的规模杠杆。

三个覆盖 80% 诊断场景的形态，避免每个新 Skill 都写专用解析器：
  generic/kv-num-v1   `key value` / `key: value` 行 → output.<key>=数值
  generic/count-v1    行数与首个数值 → output.count / output.value
  generic/table-v1    带表头的空白分隔表 → rows[{列名: 值}]

设计取舍（诚实声明）：通用解析器不做字段静态声明（键名由输出决定），
FIELD 静态检查因此对它跳过——换来的是批量速度。纪律补偿见 docs/07 B12：
分支表达式只允许引用该形态定义上必然产出的字段；专用解析器仍是首选，
generic 是"没有更准的解析器时"的兜底。

键名归一化：小写、非字母数字一律折成下划线（`Total Sessions:` → total_sessions），
保证分支表达式可预测地引用。
"""
import re

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _norm_key(k):
    k = re.sub(r"[^0-9a-zA-Z]+", "_", k.strip().lower()).strip("_")
    return k or "field"


def _to_num(s):
    m = _NUM.search(s.replace(",", ""))
    if not m:
        return None
    v = m.group(0)
    return float(v) if "." in v else int(v)


def parse_kv_num(text):
    """`key value` / `key: value` / `key = value` 行 → 数值标量（非数值行忽略）。"""
    out = {}
    for line in (text or "").splitlines():
        m = re.match(r"\s*([^:=]+?)\s*[:=]?\s+(-?[\d,.]+)\s*\S*\s*$", line)
        if m:
            v = _to_num(m.group(2))
            if v is not None:
                out[_norm_key(m.group(1))] = v
    return {"output": out}


def parse_count(text):
    """输出行数 + 首个数值。覆盖 `... | wc -l`、单数值输出、grep 计数等。"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    v = _to_num(text or "")
    return {"output": {"count": len(lines), "value": v if v is not None else 0},
            "lines": lines}


def parse_table(text):
    """首个非空行当表头（空白分隔），其余行按列对齐 → rows。数值列自动转数。
    列数多于表头的，多余部分并入最后一列（路径/描述常含空格）。"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return {"rows": []}
    headers = [_norm_key(h) for h in lines[0].split()]
    rows = []
    for ln in lines[1:]:
        parts = ln.split()
        if not parts:
            continue
        if len(parts) > len(headers):
            parts = parts[:len(headers) - 1] + [" ".join(parts[len(headers) - 1:])]
        row = {}
        for h, p in zip(headers, parts):
            n = _to_num(p)
            row[h] = n if n is not None and re.fullmatch(r"-?[\d,.]+%?", p) else p
        rows.append(row)
    return {"rows": rows, "output": {"row_count": len(rows)}}


def install(register):
    # 刻意不带字段声明：键名动态，FIELD 检查跳过（docs/07 B12 有纪律补偿）
    register("generic/kv-num-v1", parse_kv_num)
    register("generic/count-v1", parse_count)
    register("generic/table-v1", parse_table)
