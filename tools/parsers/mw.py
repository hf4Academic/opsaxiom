"""
中间件解析器（T-1 起，按需实现）。先实现导航档演示所需的 mysql 两个，
其余 middleware 解析器契约在 parser_fields.yaml 声明，随用随补。
"""
import re


def _pairs(text):
    """解析 'Name<空白>数字' 每行（SHOW STATUS / 简单聚合结果通用）。"""
    d = {}
    for ln in text.splitlines():
        m = re.match(r"(.+?)\s+(-?\d+)\s*$", ln.strip())
        if m:
            d[m.group(1).strip().lower()] = int(m.group(2))
    return d


def parse_mysql_status(text):
    d = _pairs(text)
    return {
        "max_query_time": d.get("max_query_time") or d.get("max_time") or d.get("max(time)"),
        "slow_queries": d.get("slow_queries"),
        "connected": d.get("threads_connected") or d.get("connected"),
        "max_connections": d.get("max_connections"),
    }


def parse_mysql_procstate(text):
    wl = sd = 0
    for ln in text.splitlines():
        m = re.match(r"(.+?)\s+(\d+)\s*$", ln.strip())
        if m:
            name, c = m.group(1).lower(), int(m.group(2))
            if "lock" in name:
                wl += c
            if "sending data" in name:
                sd += c
    return {"waiting_lock": wl, "sending_data": sd}


def install(register):
    register("mysql/status-v1", parse_mysql_status,
             {"scalars": ["max_query_time", "slow_queries", "connected", "max_connections"]})
    register("mysql/procstate-v1", parse_mysql_procstate,
             {"scalars": ["waiting_lock", "sending_data"]})
