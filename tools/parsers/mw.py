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


def parse_mysql_conn(text):
    """SHOW STATUS/VARIABLES 的 Threads_connected + max_connections → 派生 conn_ratio。
    （G-4；exprlang 无除法，比例在解析器算好，B6）。"""
    d = _pairs(text)
    tc = int(d.get("threads_connected") or d.get("threads_connected".title()) or 0)
    mc = int(d.get("max_connections") or 0)
    ratio = round(tc / mc, 3) if mc else 0.0
    return {"output": {"threads_connected": tc, "max_connections": mc,
                       "conn_ratio": ratio}}


def parse_mysql_processlist_agg(text):
    """processlist 聚合行（user host command COUNT SUM(Sleep)）→ sleep_count + 派生 sleep_ratio。
    宽松认：每行末两个整数为 总数、Sleep 数；取首行 user 为 top_user。"""
    total = sleep = 0
    top_user = ""
    for ln in text.splitlines():
        m = re.search(r"(\S+).*?(\d+)\s+(\d+)\s*$", ln.strip())
        if m:
            if not top_user:
                top_user = m.group(1)
            total += int(m.group(2))
            sleep += int(m.group(3))
    ratio = round(sleep / total, 3) if total else 0.0
    return {"output": {"conn_total": total, "sleep_count": sleep,
                       "sleep_ratio": ratio, "top_user": top_user}}


def install(register):
    register("mysql/status-v1", parse_mysql_status,
             {"scalars": ["max_query_time", "slow_queries", "connected", "max_connections"]})
    register("mysql/procstate-v1", parse_mysql_procstate,
             {"scalars": ["waiting_lock", "sending_data"]})
    register("mysql/conn-v1", parse_mysql_conn,
             {"scalars": ["threads_connected", "max_connections", "conn_ratio"]})
    register("mysql/processlist-agg-v1", parse_mysql_processlist_agg,
             {"scalars": ["conn_total", "sleep_count", "sleep_ratio", "top_user"]})
