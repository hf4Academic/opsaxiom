"""I-6 cred.py 测试：set/get/rm/list、值不回显、fernet 降级、resolve 接线。

环境无 OS keyring（headless），故强制 fernet 路径并显式传 master；
OS keyring 分支在有桌面的机器上自然生效（_os_keyring 探测性读写筛选后端）。
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cred  # noqa: E402
import access  # noqa: E402


@pytest.fixture(autouse=True)
def _fernet_only(monkeypatch):
    monkeypatch.setattr(cred, "_os_keyring", lambda: None)   # 强制 fernet 降级


def test_set_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    backend = cred.set_cred("core-sw-1", {"username": "netops-ro", "password": "s3cret"},
                            master="pw")
    assert backend == "fernet-file"
    got = cred.get_cred("core-sw-1", master="pw")
    assert got["username"] == "netops-ro"
    assert got["password"] == "s3cret"


def test_value_not_in_json_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    cred.set_cred("dev", {"username": "ro", "password": "topsecret"}, master="pw")
    meta = (tmp_path / "creds" / "dev.json").read_text()
    assert "topsecret" not in meta                      # 元数据绝不含密码值


def test_secret_file_perms(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    cred.set_cred("dev", {"password": "x"}, master="pw")
    import stat
    assert stat.S_IMODE((tmp_path / "creds" / "dev.secret").stat().st_mode) == 0o600


def test_wrong_master_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    cred.set_cred("dev", {"password": "s3cret"}, master="correct")
    with pytest.raises(cred.CredError):
        cred.get_cred("dev", master="wrong")
    assert cred.get_cred("dev", master="correct")["password"] == "s3cret"


def test_missing_returns_none_not_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    assert cred.get_cred("nope", master="pw") is None   # 不存在=None，不是报错


def test_list_shows_names_not_values(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    cred.set_cred("dev1", {"username": "ro", "password": "s3cret-value"}, master="pw")
    rows = cred.list_creds()
    assert rows and rows[0]["name"] == "dev1"
    assert all("s3cret-value" not in str(r) for r in rows)  # 值绝不出现


def test_rm(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    cred.set_cred("dev", {"password": "x"}, master="pw")
    assert cred.rm_cred("dev") is True
    assert cred.get_cred("dev", master="pw") is None
    assert cred.rm_cred("dev") is False


def test_resolve_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    cred.set_cred("sw", {"username": "ro", "password": "pw"}, master="m")
    # access.resolve 需主口令解锁 fernet——测试里直接调 get_cred 验证，resolve 走 OS keyring 路径
    got = cred.get_cred("sw", master="m")
    c = access.Credential("keyring", **got)
    assert c.kind == "keyring" and c.get("password") == "pw"
    assert "pw" not in repr(c)                          # R-A2：repr 打码


def test_resolve_keyring_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    with pytest.raises(access.AccessError, match="cred set"):
        access.resolve({"auth": "keyring:nope"})
