"""
自研表格类解析器：把系统命令的定宽/空白分隔输出转成 rows 列表。
每个解析器返回 {"rows": [ {列: 值}, ... ]}，数值列尽量转成 int/float。

覆盖金标准依赖：table/df-v1, table/df-inode-v1, table/du-v1。
其余 O-3/O-4 引用的解析器（vmstat/ps/iostat...）留待后续补齐，
本模块提供通用工具函数便于扩展。
"""
import re


def _pct(s):
    """'75%' -> 75 (int)；非法返回 None。"""
    m = re.match(r"\s*(\d+)\s*%\s*$", s)
    return int(m.group(1)) if m else None


def _int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def parse_df(text):
    """df -B1 --output=target,size,used,avail,pcent 的输出。
    表头行含 'Mounted on' 或列名，跳过；每行末列是百分比。"""
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("filesystem", "mounted", "target")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pct = _pct(parts[-1])
        if pct is None:
            continue  # 非数据行
        # 约定列顺序：target size used avail pcent（target 可能含空格，用末4列反推）
        target = " ".join(parts[:-4]) if len(parts) >= 5 else parts[0]
        size, used, avail = (_int(x) for x in parts[-4:-1])
        rows.append({"target": target, "size": size, "used": used,
                     "avail": avail, "pcent": pct})
    return {"rows": rows}


def parse_df_inode(text):
    """df -i --output=target,itotal,iused,ipcent 的输出。"""
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("filesystem", "target", "inodes")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pct = _pct(parts[-1])
        if pct is None:
            continue
        target = " ".join(parts[:-3]) if len(parts) >= 4 else parts[0]
        itotal, iused = (_int(x) for x in parts[-3:-1])
        rows.append({"target": target, "itotal": itotal, "iused": iused, "ipcent": pct})
    return {"rows": rows}


def parse_du(text):
    """du -xB1 ... | sort -rn | head 的输出：每行 '<bytes>\\t<path>'。"""
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        size = _int(parts[0])
        if size is None:
            continue
        rows.append({"size": size, "path": parts[1]})
    return {"rows": rows}


def install(register):
    register("table/df-v1", parse_df)
    register("table/df-inode-v1", parse_df_inode)
    register("table/du-v1", parse_du)
