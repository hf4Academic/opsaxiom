"""U-3 obs/sec 解析器单测（JSON 输入 → 契约标量）。"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import parsers  # noqa: E402


def test_alerts_derives_share():
    d = parsers.get_parser("obs/alerts-v1")(json.dumps(
        {"active_alerts": 300, "groups": {"NodeDown": 210, "HighLatency": 90}}))
    assert d["top_group_count"] == 210
    assert d["top_group_share"] == 70          # 210/300


def test_target_classifies_error():
    refused = parsers.get_parser("obs/target-v1")(json.dumps({"up": 0, "last_error": "connection refused"}))
    assert refused["last_error_conn_refused"] == 1 and refused["last_error_timeout"] == 0
    timeout = parsers.get_parser("obs/target-v1")(json.dumps({"up": 0, "last_error": "context deadline exceeded (timeout)"}))
    assert timeout["last_error_timeout"] == 1


def test_cert_inv_buckets():
    d = parsers.get_parser("sec/cert-inv-v1")(json.dumps(
        {"certs": [{"days_left": -2}, {"days_left": 5}, {"days_left": 20}, {"days_left": 200}]}))
    assert d["expired_count"] == 1
    assert d["expiring_7d_count"] == 1
    assert d["expiring_30d_count"] == 2        # 5 和 20 都 <30
    assert d["min_days_left"] == -2
    assert d["total_certs"] == 4


def test_vuln_fixable_flag():
    d = parsers.get_parser("sec/vuln-v1")(json.dumps(
        {"critical_count": 2, "high_count": 5, "fixable_critical": True, "kev_count": 0}))
    assert d["has_fix_critical"] == 1


def test_bad_json_safe():
    d = parsers.get_parser("sec/authfail-v1")("garbage")
    assert d["failed_count"] is None
