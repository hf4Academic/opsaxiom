"""
训练侧指标解析器（U-2）——配套 opsaxiom-collect 的 JSON 输出。

collect 恒输出单行 JSON，这里 json.loads 后按解析器契约挑出标量/行，
缺字段留 None（决策树的 when 求值缺字段→None→不命中，安全）。
非 JSON（采集异常/空）→ 返回空结构，树走 otherwise。
"""
import json


def _load(text):
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def parse_step_time(text):
    d = _load(text)
    return {
        "rows": d.get("rows", []),
        "max_step_ms": d.get("max_step_ms"),
        "median_step_ms": d.get("median_step_ms"),
    }


def parse_node_metrics(text):
    d = _load(text)
    return {
        "gpu_clock_throttled": d.get("gpu_clock_throttled"),
        "ib_rate_degraded": d.get("ib_rate_degraded"),
        "data_wait_ms": d.get("data_wait_ms"),
        "median_step_ms": d.get("median_step_ms"),
    }


def parse_gpu_trace(text):
    d = _load(text)
    return {
        "comm_time_pct": d.get("comm_time_pct"),
        "small_kernel_pct": d.get("small_kernel_pct"),
    }


def install(register):
    register("train/step-time-v1", parse_step_time,
             {"rows": ["node", "step_ms"], "scalars": ["max_step_ms", "median_step_ms"]})
    register("train/node-metrics-v1", parse_node_metrics,
             {"scalars": ["gpu_clock_throttled", "ib_rate_degraded", "data_wait_ms", "median_step_ms"]})
    register("train/gpu-trace-v1", parse_gpu_trace,
             {"scalars": ["comm_time_pct", "small_kernel_pct"]})
