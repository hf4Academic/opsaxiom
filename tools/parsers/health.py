"""
健康/派生字段解析器（Q-2）——实现 R-5/F-8 累积的 verify.assert 与派生字段契约。
这些解析器把命令输出转成决策树需要的标量健康字段，是"确定性工具层"的一部分（R9）。
每个都带字段声明并有真实解析逻辑（可测），不是占位。
"""
import re


def parse_systemctl_active(text):
    """`systemctl is-active X [Y...]` 输出 → service_active。
    任一单元 active 即真（覆盖 clock-drift 的 chronyd/timesyncd 二选一、agent-deploy 单服务）。"""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    active = any(ln == "active" for ln in lines)
    # metrics_ok：若命令串接了 curl /metrics（agent-deploy），输出里出现指标行则真
    metrics_ok = bool(re.search(r"^\s*(#|node_|[a-z_]+\{)", text, re.M))
    return {"service_active": active, "metrics_ok": metrics_ok}


def parse_systemctl_show(text):
    """`systemctl show -p ActiveState,Result,...` 的 key=value 输出 → result/active_state。"""
    kv = {}
    for ln in text.strip().splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            kv[k.strip()] = v.strip()
    return {
        "result": kv.get("Result"),
        "active_state": kv.get("ActiveState"),
        "exit_code": _int(kv.get("ExecMainStatus")),
    }


def parse_mount_opts(text):
    """`findmnt -no OPTIONS` + dmesg 尾巴 → mount_rw / fs_errors。
    mount_rw：挂载选项含 rw 且不含 ro。fs_errors：dmesg 里新的 fs error 计数。"""
    opts_line = text.strip().splitlines()[0] if text.strip() else ""
    is_ro = bool(re.search(r"(^|,)ro(,|$)", opts_line))
    is_rw = bool(re.search(r"(^|,)rw(,|$)", opts_line)) and not is_ro
    fs_errors = len(re.findall(r"EXT4-fs error|XFS.*corruption|I/O error", text))
    return {"mount_rw": is_rw, "fs_errors": fs_errors}


def parse_conntrack(text):
    """两行 count / max（/proc/sys/net/netfilter/nf_conntrack_{count,max}）→ ct_count/ct_max。"""
    nums = [int(x) for x in re.findall(r"^\s*(\d+)\s*$", text, re.M)]
    return {"ct_count": nums[0] if len(nums) >= 1 else None,
            "ct_max": nums[1] if len(nums) >= 2 else None}


def parse_loadavg(text):
    """`cat /proc/loadavg && nproc` → load1/load5/load15（cores 由 fact 提供）。"""
    m = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", text)
    return {
        "load1": float(m.group(1)) if m else None,
        "load5": float(m.group(2)) if m else None,
        "load15": float(m.group(3)) if m else None,
    }


def parse_rollout_status(text):
    """`kubectl rollout status` + `get pods` → rollout_succeeded/unready_pods。"""
    succeeded = "successfully rolled out" in text
    # 统计就绪列为 false 的 Pod 行（jsonpath 输出 name phase ready）
    unready = len(re.findall(r"\bfalse\b", text))
    return {"rollout_succeeded": succeeded, "unready_pods": unready}


def _int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def install(register):
    register("text/systemctl-active-v1", parse_systemctl_active,
             {"scalars": ["service_active", "metrics_ok"], "lines": True})
    register("json/systemctl-show-v1", parse_systemctl_show,
             {"scalars": ["result", "active_state", "exit_code"], "lines": False})
    register("text/mount-opts-v1", parse_mount_opts,
             {"scalars": ["mount_rw", "fs_errors"], "lines": True})
    register("json/conntrack-v1", parse_conntrack,
             {"scalars": ["ct_count", "ct_max"], "lines": False})
    register("json/loadavg-v1", parse_loadavg,
             {"scalars": ["load1", "load5", "load15"], "lines": False})
    register("json/rollout-status-v1", parse_rollout_status,
             {"scalars": ["rollout_succeeded", "unready_pods"], "lines": False})
