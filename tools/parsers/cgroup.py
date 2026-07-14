"""cgroup 解析器（G-1）——CPU 限流诊断用。

cgroup v1 与 v2 的文件格式不同，两者都要认（cpu.stat 的 throttled 字段名 v1=throttled_time
纳秒 / v2=throttled_usec 微秒；cpu.max=v2 单文件 "quota period"，v1 拆两个文件）。
派生标量在 parser 内算好（exprlang 无除法，B6：判据里不做除法，解析器预派生）。
"""
import re


def _kv(text):
    d = {}
    for line in (text or "").splitlines():
        p = line.split()
        if len(p) >= 2:
            try:
                d[p[0]] = int(p[1])
            except ValueError:
                pass
    return d


def parse_cpu_stat(text):
    """cpu.stat（v1/v2 通用 key value 行）→ 限流计数 + 派生 throttle_ratio。"""
    d = _kv(text)
    periods = d.get("nr_periods", 0)
    throttled = d.get("nr_throttled", 0)
    tusec = d.get("throttled_usec", d.get("throttled_time", 0))
    ratio = round(throttled / periods, 3) if periods else 0.0
    return {"output": {"nr_periods": periods, "nr_throttled": throttled,
                       "throttled_usec": tusec, "throttle_ratio": ratio}}


def parse_cpu_max(text):
    """cpu.max（v2 "quota period" 或 "max period"）→ quota_cores。
    quota=max(无限制) → quota_cores = -1。v1 若只喂到 quota 数字也兼容。"""
    t = (text or "").strip()
    m = re.match(r"(\S+)\s+(\d+)", t)
    quota, period = None, None
    if m:
        q, period = m.group(1), int(m.group(2))
        quota = None if q == "max" else int(q)
    else:                                   # 仅一个数字（v1 cfs_quota_us，period 取默认 100000）
        m2 = re.match(r"(-?\d+)", t)
        if m2:
            v = int(m2.group(1))
            quota = None if v < 0 else v
            period = 100000
    if period and quota is not None:
        cores = round(quota / period, 2)
    elif quota is None and period:
        cores = -1.0                        # unlimited
    else:
        cores = 0.0
    return {"output": {"quota_cores": cores}}


def install(register):
    register("cgroup/cpu-stat-v1", parse_cpu_stat,
             {"scalars": ["nr_periods", "nr_throttled", "throttled_usec", "throttle_ratio"],
              "lines": False})
    register("cgroup/cpu-max-v1", parse_cpu_max,
             {"scalars": ["quota_cores"], "lines": False})
