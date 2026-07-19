"""I-0 access.py 金标准测试——三条红线的对抗覆盖。"""
import os
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import access  # noqa: E402


def _write(tmp_path, targets):
    f = tmp_path / "targets.yaml"
    f.write_text(yaml.safe_dump({"targets": targets}, allow_unicode=True), encoding="utf-8")
    return f


def test_load_ok(tmp_path):
    f = _write(tmp_path, {
        "web-01": {"connector": "ssh", "host": "10.0.1.11", "auth": "agent"},
        "web-02": {"connector": "ssh", "host": "10.0.1.12", "auth": "ssh_config"},
        "sw-1": {"connector": "network", "host": "10.255.0.1", "auth": "keyring:sw-1",
                 "reach": "vpn:office"},
        "k8s": {"connector": "kubectl", "auth": "kubeconfig", "context": "prod"},
    })
    ts = access.load_targets(f)
    assert set(ts) == {"web-01", "web-02", "sw-1", "k8s"}


# ---- R-A1：明文凭证拒绝加载（对抗用例）----

@pytest.mark.parametrize("bad", [
    {"connector": "ssh", "host": "h", "password": "hunter2"},
    {"connector": "ssh", "host": "h", "Token": "abcdef"},          # 大小写混淆
    {"connector": "http", "base": "http://x", "api_key": "k-123"},
    {"connector": "ssh", "host": "h", "auth": "password:hunter2"},  # auth 里塞密码
    {"connector": "ssh", "host": "h", "auth": "hunter2"},           # 非法引用形态
])
def test_plaintext_credential_rejected(tmp_path, bad):
    f = _write(tmp_path, {"t": bad})
    with pytest.raises(access.AccessError):
        access.load_targets(f)


def test_one_bad_entry_rejects_whole_file(tmp_path):
    """红线不做部分放行：一条违规整个文件拒绝，逼修复而非静默跳过。"""
    f = _write(tmp_path, {
        "good": {"connector": "ssh", "host": "h", "auth": "agent"},
        "bad": {"connector": "ssh", "host": "h", "password": "x"},
    })
    with pytest.raises(access.AccessError, match="bad"):
        access.load_targets(f)


# ---- R-A3：只读 scope ----

def test_write_scope_rejected(tmp_path):
    f = _write(tmp_path, {"t": {"connector": "ssh", "host": "h",
                                "auth": "agent", "scope": "write"}})
    with pytest.raises(access.AccessError, match="readonly"):
        access.load_targets(f)


# ---- R-A2：凭证对象不出内存 ----

def test_credential_repr_masked_and_unserializable():
    c = access.Credential("agent", sock="/tmp/agent.sock", material="SECRET")
    assert "SECRET" not in repr(c) and "sock" not in repr(c)
    import pickle
    with pytest.raises(access.AccessError):
        pickle.dumps(c)
    with pytest.raises(Exception):
        yaml.safe_dump(c)


# ---- P0 解析 ----

def test_resolve_agent_requires_sock(monkeypatch):
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    with pytest.raises(access.AccessError, match="ssh-agent"):
        access.resolve({"auth": "agent"})
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    assert access.resolve({"auth": "agent"}).kind == "agent"


def test_resolve_keyring_points_to_cred_set():
    with pytest.raises(access.AccessError, match="cred set"):
        access.resolve({"auth": "keyring:sw-1"})


def test_missing_file_is_empty(tmp_path):
    assert access.load_targets(tmp_path / "nope.yaml") == {}
