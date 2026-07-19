"""I-1 执行门对抗测试：写命令/注入/未授权拒绝，凭证不入审计。"""
import json
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import gate  # noqa: E402


def _setup(tmp_path, monkeypatch, authorized=True):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/fake-agent.sock")  # resolve(agent) 需要
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {
        "web-01": {"connector": "ssh", "host": "10.0.0.9", "user": "opsaxiom-ro",
                   "auth": "agent"},
    }}, allow_unicode=True), encoding="utf-8")
    if authorized:
        (tmp_path / "trust.yaml").write_text(
            yaml.safe_dump({"auto_exec": ["web-01"]}), encoding="utf-8")
    # 记录凭证材料，供"凭证不入审计"断言
    SECRET = "SECRET-KEY-MATERIAL-xyz"

    def fake_conn(target, cred, cmd):
        # 连接器不做安全判断——只回显；把秘密塞进 cred 以验证它不外泄
        cred._kw["material"] = SECRET
        return 0, f"ran:{cmd}", ""
    return fake_conn, SECRET


def test_readonly_command_passes(tmp_path, monkeypatch):
    fn, _ = _setup(tmp_path, monkeypatch)
    out = gate.run_remote("web-01", "cat /proc/loadavg", connector_fn=fn, now="T")
    assert out == "ran:cat /proc/loadavg"


@pytest.mark.parametrize("cmd", [
    "rm -rf /data", "tee /etc/passwd", "echo x > /etc/hosts",
    "cat /etc/shadow && reboot", "dd if=/dev/zero of=/dev/sda",
])
def test_write_commands_rejected(tmp_path, monkeypatch, cmd):
    fn, _ = _setup(tmp_path, monkeypatch)
    with pytest.raises(gate.GateError):
        gate.run_remote("web-01", cmd, connector_fn=fn, now="T")


def test_param_injection_rejected(tmp_path, monkeypatch):
    fn, _ = _setup(tmp_path, monkeypatch)
    # 命令本身过只读白名单（grep 前导、无写词），但 param 值含命令替换元字符——
    # 这正是 T-3 要拦的：模板可信、param 值不可信。
    cmd = "grep abc$(id) /var/log/app.log"
    with pytest.raises(gate.GateError, match="注入"):
        gate.run_remote("web-01", cmd, params={"pat": "abc$(id)"},
                        connector_fn=fn, now="T")


def test_unauthorized_target_rejected(tmp_path, monkeypatch):
    fn, _ = _setup(tmp_path, monkeypatch, authorized=False)
    with pytest.raises(gate.GateError, match="未授权"):
        gate.run_remote("web-01", "uptime", connector_fn=fn, now="T")


def test_unknown_target_rejected(tmp_path, monkeypatch):
    fn, _ = _setup(tmp_path, monkeypatch)
    with pytest.raises(gate.GateError, match="未知目标"):
        gate.run_remote("nope", "uptime", connector_fn=fn, now="T")


def test_credential_never_in_audit(tmp_path, monkeypatch):
    fn, SECRET = _setup(tmp_path, monkeypatch)
    gate.run_remote("web-01", "uptime", connector_fn=fn, now="T")
    audit = (tmp_path / "audit" / "remote.jsonl").read_text(encoding="utf-8")
    assert SECRET not in audit                       # 凭证材料绝不落审计
    rec = json.loads(audit.splitlines()[-1])
    assert rec["decision"] == "allow" and rec["cred_kind"] == "agent"
    assert "material" not in audit and "sock" not in audit


def test_denials_are_audited(tmp_path, monkeypatch):
    fn, _ = _setup(tmp_path, monkeypatch)
    with pytest.raises(gate.GateError):
        gate.run_remote("web-01", "rm -rf /", connector_fn=fn, now="T")
    rec = json.loads((tmp_path / "audit" / "remote.jsonl").read_text().splitlines()[-1])
    assert rec["decision"] == "deny"                 # 被拦的写命令也留痕（安全事件）


def test_network_connector_not_wired_yet(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {
        "sw": {"connector": "network", "host": "10.1.1.1", "auth": "keyring:sw"}}},
        allow_unicode=True), encoding="utf-8")
    (tmp_path / "trust.yaml").write_text(yaml.safe_dump({"auto_exec": ["sw"]}))
    with pytest.raises(gate.GateError, match="I-5"):
        gate.run_remote("sw", "display version")
