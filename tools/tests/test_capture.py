"""V-2 经验捕获三通道测试。"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import capture  # noqa: E402


def _seed_audit(home, sid, recs):
    d = home / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs))


def test_from_session_builds_valid_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)          # skills-drafts 落到临时目录
    # capture 的 ROOT 固定在仓库；draft 落仓库 skills-drafts。用真 sid 名避免碰撞
    _seed_audit(tmp_path, "t_capture", [
        {"node": "look", "type": "check", "cmd": "df -h /", "output": "Use% 95%"},
        {"node": "big", "type": "check", "cmd": "du -x /", "output": "8G /var/log"},
        {"node": "fb", "type": "feedback", "answer": "👍"},
    ])
    sf = capture.from_session("t_capture", "host.storage.t-capture", "测试捕获", "host/storage/t-capture")
    try:
        rep, gaps = capture.lint(sf)
        assert not rep.errors, [i for i in rep.items if i[0] == "ERROR"]   # 结构+S5 通过
        assert gaps                       # 有待补 TODO
        import yaml
        s = yaml.safe_load(pathlib.Path(sf).read_text())
        assert s["tree"]["entry"] == "look"
        assert [n["id"] for n in s["tree"]["nodes"] if n["type"] == "check"] == ["look", "big"]
        assert s["metadata"]["provenance"]["generated_by"] == "human-session"
    finally:
        import shutil
        shutil.rmtree(sf.parent, ignore_errors=True)


def test_record_rejects_write_command(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    capture.record_start("wtest")
    try:
        capture.record_exec("rm -rf /tmp/x")
        assert False, "写命令应被拒绝"
    except PermissionError:
        pass
    finally:
        capture.record_stop()


def test_record_captures_readonly(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    capture.record_start("rtest")
    step, summ = capture.record_exec("echo hello")
    assert step == "step_1"
    sid = capture.record_stop()
    recs = capture._read_audit(sid)
    assert recs[0]["cmd"] == "echo hello"


def test_wizard_builds_valid_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    ans = iter(["测试向导", "host/x/wiz", "1", "cat /proc/loadavg", "坑提醒",
                "count(rows)>0", "结论A"])
    sf = capture.wizard(inp=lambda p: next(ans))
    try:
        rep, _ = capture.lint(sf)
        assert not rep.errors
        import yaml
        s = yaml.safe_load(pathlib.Path(sf).read_text())
        assert s["metadata"]["provenance"]["generated_by"] == "human-wizard"
    finally:
        import shutil
        shutil.rmtree(sf.parent, ignore_errors=True)
