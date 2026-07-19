"""I-5 network/http 只读闸门对抗测试（经 gate）。"""
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import gate  # noqa: E402


def _setup(tmp_path, monkeypatch, connector, target):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/fake.sock")
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {"dev": target}},
        allow_unicode=True), encoding="utf-8")
    (tmp_path / "trust.yaml").write_text(yaml.safe_dump({"auto_exec": ["dev"]}),
                                         encoding="utf-8")
    return lambda t, c, cmd: (0, "ok", "")


NET = {"connector": "network", "host": "10.1.1.1", "user": "ro",
       "auth": "keyring:dev", "platform": "cisco_ios"}
HTTP = {"connector": "http", "base": "https://es.local:9200", "auth": "keyring:dev"}


# ---- network：只读 show 放行，配置/提权拒绝 ----

@pytest.mark.parametrize("cmd", ["show version", "show ip bgp summary",
                                 "show ip ospf neighbor"])
def test_network_readonly_allowed(tmp_path, monkeypatch, cmd):
    fn = _setup(tmp_path, monkeypatch, "network", NET)
    # keyring 凭证 I-6 未接 → resolve 会报错；把 auth 换成 agent 以隔离白名单判定
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    t = dict(NET); t["auth"] = "agent"
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {"dev": t}}))
    out = gate.run_remote("dev", cmd, connector_fn=fn, now="T")
    assert out == "ok"


@pytest.mark.parametrize("cmd", [
    "enable", "configure terminal", "conf t", "write memory", "copy running-config startup-config",
    "show running-config | no shutdown", "erase startup-config", "reload",
    "clear ip bgp *",                     # clear 是写性操作（软复位）→ 拒
    "confreg 0x2142",
])
def test_network_config_rejected(tmp_path, monkeypatch, cmd):
    fn = _setup(tmp_path, monkeypatch, "network", NET)
    t = dict(NET); t["auth"] = "agent"
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {"dev": t}}))
    with pytest.raises(gate.GateError):
        gate.run_remote("dev", cmd, connector_fn=fn, now="T")


def test_network_unknown_prefix_rejected(tmp_path, monkeypatch):
    fn = _setup(tmp_path, monkeypatch, "network", NET)
    t = dict(NET); t["auth"] = "agent"
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {"dev": t}}))
    # 只读首词但前缀不在语法库（疑似幻觉/混用）→ 拒
    with pytest.raises(gate.GateError):
        gate.run_remote("dev", "show the-magic-unicorn", connector_fn=fn, now="T")


# ---- http：GET 放行，写方法拒绝 ----

def test_http_get_allowed(tmp_path, monkeypatch):
    fn = _setup(tmp_path, monkeypatch, "http", HTTP)
    t = dict(HTTP); t["auth"] = "agent"        # keyring 未接(I-6)，隔离白名单判定
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {"dev": t}}))
    out = gate.run_remote("dev", "/_cat/indices", params={"method": "GET"},
                          connector_fn=fn, now="T")
    assert out == "ok"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "put"])
def test_http_write_methods_rejected(tmp_path, monkeypatch, method):
    fn = _setup(tmp_path, monkeypatch, "http", HTTP)
    t = dict(HTTP); t["auth"] = "agent"
    (tmp_path / "targets.yaml").write_text(yaml.safe_dump({"targets": {"dev": t}}))
    with pytest.raises(gate.GateError):
        gate.run_remote("dev", "/_cat/indices", params={"method": method},
                        connector_fn=fn, now="T")
