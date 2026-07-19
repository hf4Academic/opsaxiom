"""I-2 per-target 授权 TTL / revoke / list 测试。"""
import datetime
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import sweep  # noqa: E402

T0 = datetime.datetime(2026, 1, 1, 12, 0, 0)


def _f(tmp_path):
    return tmp_path / "trust.yaml"


def test_grant_and_within_ttl(tmp_path):
    f = _f(tmp_path)
    sweep.grant_trust("web-01", path=f, ttl_days=30, now=T0)
    assert sweep.is_trusted("web-01", path=f, now=T0 + datetime.timedelta(days=29))


def test_expired_is_untrusted(tmp_path):
    f = _f(tmp_path)
    sweep.grant_trust("web-01", path=f, ttl_days=30, now=T0)
    assert not sweep.is_trusted("web-01", path=f, now=T0 + datetime.timedelta(days=31))


def test_local_no_expiry(tmp_path):
    f = _f(tmp_path)
    sweep.grant_trust("__local__", path=f, ttl_days=None, now=T0)
    assert sweep.is_trusted("__local__", path=f, now=T0 + datetime.timedelta(days=9999))


def test_legacy_auto_exec_still_trusted(tmp_path):
    f = _f(tmp_path)
    f.write_text(yaml.safe_dump({"auto_exec": ["__local__"]}), encoding="utf-8")
    assert sweep.is_trusted("__local__", path=f)


def test_revoke(tmp_path):
    f = _f(tmp_path)
    sweep.grant_trust("web-01", path=f, ttl_days=30, now=T0)
    assert sweep.revoke_trust("web-01", path=f) is True
    assert not sweep.is_trusted("web-01", path=f, now=T0)
    assert sweep.revoke_trust("web-01", path=f) is False   # 幂等：无授权返回 False


def test_revoke_clears_legacy(tmp_path):
    f = _f(tmp_path)
    f.write_text(yaml.safe_dump({"auto_exec": ["old-host"]}), encoding="utf-8")
    assert sweep.revoke_trust("old-host", path=f) is True
    assert not sweep.is_trusted("old-host", path=f)


def test_list_grants(tmp_path):
    f = _f(tmp_path)
    sweep.grant_trust("web-01", path=f, ttl_days=30, now=T0)
    sweep.grant_trust("web-02", path=f, ttl_days=30, now=T0 - datetime.timedelta(days=40))
    rows = {r["target"]: r for r in sweep.list_grants(path=f, now=T0)}
    assert rows["web-01"]["remaining_days"] > 0 and not rows["web-01"]["expired"]
    assert rows["web-02"]["expired"]                       # 40 天前授权、30 天 TTL → 过期
