"""V-3 一键认证：run 终点接单 + meta.json 留存 + --from-session 预填。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import runtime  # noqa: E402


def _disk_full_skill():
    return next(x for x in (ROOT / "skills").rglob("skill.yaml")
                if yaml.safe_load(x.read_text())["metadata"]["id"] == "host.storage.capacity.disk-full")


def test_run_terminal_generates_signed_attestation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    a = yaml.safe_load((ROOT / "demos" / "disk-full-guided.answers.yaml").read_text())
    a["answers"]["done_ok:attest"] = {"os_family": "rhel", "scale": 47, "attestor": "gh:t"}
    io = runtime.IO(answers=a["answers"], echo=False)
    sess = runtime.Session(_disk_full_skill(), params=a["params"], mode="guided", io=io, sid="v3t")
    r = sess.run()
    assert r["outcome"] == "done"
    # meta.json 留存
    assert (tmp_path / "sessions" / "v3t.meta.json").exists()
    # attestation 生成且签名
    adir = ROOT / "skills" / "host" / "disk-full" / "attestations"
    made = list(adir.glob("*.yaml")) if adir.exists() else []
    try:
        assert made, "run 终点应生成 attestation"
        att = yaml.safe_load(made[0].read_text())
        assert att["skill"] == "host.storage.capacity.disk-full"
        assert att["mode"] == "navigator"
        assert att["signature"].startswith("ed25519:") or att["signature"].startswith("hmac:")
    finally:
        for m in made:
            m.unlink()
        if adir.exists() and not any(adir.iterdir()):
            adir.rmdir()


def test_negative_feedback_records_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    a = yaml.safe_load((ROOT / "demos" / "disk-full-guided.answers.yaml").read_text())
    a["answers"]["done_ok:fb"] = "👎"
    a["answers"]["done_ok:attest"] = {"os_family": "rhel", "scale": 5, "attestor": "gh:t"}
    io = runtime.IO(answers=a["answers"], echo=False)
    sess = runtime.Session(_disk_full_skill(), params=a["params"], mode="guided", io=io, sid="w3neg")
    sess.run()
    adir = ROOT / "skills" / "host" / "disk-full" / "attestations"
    made = list(adir.glob("*.yaml")) if adir.exists() else []
    try:
        assert made
        att = yaml.safe_load(made[0].read_text())
        assert att["outcome"] == "partial"       # 👎 → partial
    finally:
        for m in made:
            m.unlink()
        if adir.exists() and not any(adir.iterdir()):
            adir.rmdir()


def test_outcome_mapping():
    assert runtime.Session._outcome_from_feedback("👎") == "partial"
    assert runtime.Session._outcome_from_feedback("👍") == "resolved"
    assert runtime.Session._outcome_from_feedback("") == "resolved"


def test_skip_attest_when_no_intake(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    a = yaml.safe_load((ROOT / "demos" / "disk-full-guided.answers.yaml").read_text())
    # 无 done_ok:attest 键 → 跳过，不生成
    io = runtime.IO(answers=a["answers"], echo=False)
    sess = runtime.Session(_disk_full_skill(), params=a["params"], mode="guided", io=io, sid="v3skip")
    sess.run()
    adir = ROOT / "skills" / "host" / "disk-full" / "attestations"
    assert not (adir.exists() and any(adir.iterdir()))
