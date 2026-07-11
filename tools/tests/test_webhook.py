"""X-1 告警 webhook 入口 B 测试。"""
import pathlib
import sys
from importlib.machinery import SourceFileLoader

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
wh = SourceFileLoader("webhook", str(ROOT / "tools" / "bin" / "opsaxiom-webhook")).load_module()


def test_symptom_extraction():
    payload = {"alerts": [{"labels": {"alertname": "GPU 掉卡 XID 79", "instance": "node7"},
                           "annotations": {"description": "nvidia-smi 少了一张卡"}}]}
    s = wh.symptom_from_alert(payload)
    assert "XID 79" in s and "nvidia-smi" in s and "node7" in s


def test_card_has_run_commands():
    from opsaxiom_diagnose import diagnose_json
    hits = diagnose_json("gpu 掉卡 xid 79", top=3)
    card = wh.build_card("gpu 掉卡", hits)
    assert "opsaxiom run aicomp.gpu" in card
    assert "告警助手" in card


def test_dispatch_dry_run_no_network(capsys):
    payload = {"alerts": [{"labels": {"alertname": "kafka 积压"}}]}
    text = wh.dispatch(payload, "dingtalk", url=None, dry_run=True)
    assert "kafka" in text
    assert "run middleware.kafka" in text


def test_no_match_card_is_graceful():
    card = wh.build_card("完全无关的乱码 zzzqqq", [])
    assert "未匹配" in card and "人工" in card


def test_wrap_feishu_vs_dingtalk():
    d = wh._wrap_for("dingtalk", "**x** `y`")
    f = wh._wrap_for("feishu", "**x** `y`")
    assert d["msgtype"] == "markdown"
    assert f["msg_type"] == "text" and "**" not in f["content"]["text"]


def test_f17_card_never_leaks_credentials():
    """F-17（八轮评审）：告警自由文本夹带凭据，外发卡片必须脱敏；匹配仍用全文。"""
    payload = {"alerts": [{"labels": {"alertname": "mysql 连接满", "instance": "db-01"},
                           "annotations": {"description":
                               "密码 hunter2 mysql://root:pw@host token=ghp_abcdef123456"}}]}
    card = wh.dispatch(payload, "dingtalk", url=None, dry_run=True)
    for secret in ("hunter2", "ghp_", "root:pw"):
        assert secret not in card
    assert "connection-exhausted" in card       # 全文匹配不受脱敏影响
