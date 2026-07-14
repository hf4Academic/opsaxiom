"""DNS 解析器（G-2）——间歇性 DNS 慢/失败诊断。

resolv-v1：/etc/resolv.conf 的 nameserver 列表与 options（timeout/rotate）。
dig-multi-v1：逐 nameserver 的 dig 探测输出（ok/耗时 ms），派生死/慢 server 计数。
"""
import re


def parse_resolv(text):
    """/etc/resolv.conf → nameserver 列表 + options 形态。"""
    ns, has_timeout, has_rotate = [], False, False
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("nameserver"):
            p = line.split()
            if len(p) >= 2:
                ns.append(p[1])
        elif line.startswith("options"):
            if "timeout:" in line:
                has_timeout = True
            if "rotate" in line:
                has_rotate = True
    rows = [{"ns": x} for x in ns]
    return {"rows": rows,
            "output": {"nameserver_count": len(ns),
                       "has_timeout_opt": 1 if has_timeout else 0,
                       "has_rotate": 1 if has_rotate else 0,
                       "first_ns": ns[0] if ns else ""}}


def parse_dig_multi(text):
    """逐 server dig 探测输出 → rows[{ns, ok, ms}] + 派生 dead/slow 计数。

    认两种行形态（尽量宽松，真实 dig 输出经预处理喂进来）：
      '<ns> ok <ms>'  /  '<ns> fail'
    或原始 dig 的 'Query time: N msec' + ';; connection timed out'。
    """
    rows = []
    # 优先认预处理过的紧凑行： "10.0.0.1 ok 12" / "10.0.0.2 fail"
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+(ok|fail)(?:\s+(\d+))?", line)
        if m:
            ok = m.group(2) == "ok"
            rows.append({"ns": m.group(1), "ok": 1 if ok else 0,
                         "ms": int(m.group(3)) if m.group(3) else -1})
    dead = sum(1 for r in rows if not r["ok"])
    slow = sum(1 for r in rows if r["ok"] and r["ms"] >= 500)
    return {"rows": rows,
            "output": {"dead_ns_count": dead, "slow_ns_count": slow,
                       "probed": len(rows)}}


def install(register):
    register("dns/resolv-v1", parse_resolv,
             {"rows": ["ns"],
              "scalars": ["nameserver_count", "has_timeout_opt", "has_rotate", "first_ns"],
              "lines": False})
    register("dns/dig-multi-v1", parse_dig_multi,
             {"rows": ["ns", "ok", "ms"],
              "scalars": ["dead_ns_count", "slow_ns_count", "probed"],
              "lines": False})
