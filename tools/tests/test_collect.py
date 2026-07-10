"""U-2 opsaxiom-collect + train/* 解析器往返测试。"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import parsers  # noqa: E402

COLLECT = ROOT / "tools" / "bin" / "opsaxiom-collect"


def _run(*args):
    return subprocess.run([sys.executable, str(COLLECT), *args],
                          capture_output=True, text=True).stdout


def test_step_time_roundtrip():
    out = _run("step-time", "--job", "j1")
    d = parsers.get_parser("train/step-time-v1")(out)
    assert d["max_step_ms"] >= d["median_step_ms"]
    assert len(d["rows"]) == 8 and all("step_ms" in r for r in d["rows"])


def test_node_metrics_roundtrip():
    out = _run("node-metrics", "--job", "j1", "--node", "node3")
    d = parsers.get_parser("train/node-metrics-v1")(out)
    # 恰好命中一个根因维度（mock 三选一）
    assert d["gpu_clock_throttled"] in (0, 1)
    assert set(["gpu_clock_throttled", "ib_rate_degraded", "data_wait_ms"]) <= set(d)


def test_gpu_trace_roundtrip_and_deterministic():
    a = _run("gpu-trace", "--pid", "777")
    b = _run("gpu-trace", "--pid", "777")
    assert a == b                       # 确定性
    d = parsers.get_parser("train/gpu-trace-v1")(a)
    assert d["comm_time_pct"] is not None and d["small_kernel_pct"] is not None


def test_from_file_injection(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"comm_time_pct": 45, "small_kernel_pct": 10}))
    out = _run("gpu-trace", "--pid", "1", "--from-file", str(f))
    d = parsers.get_parser("train/gpu-trace-v1")(out)
    assert d == {"comm_time_pct": 45, "small_kernel_pct": 10}


def test_bad_json_safe():
    d = parsers.get_parser("train/gpu-trace-v1")("not json")
    assert d == {"comm_time_pct": None, "small_kernel_pct": None}
