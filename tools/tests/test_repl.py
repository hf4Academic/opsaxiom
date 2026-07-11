"""W-1 Terminal REPL 分发逻辑测试。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import repl  # noqa: E402


def test_symptom_sets_hits():
    r = repl.Repl()
    r._handle("磁盘满了但 df 还有空间")
    assert r.last_hits
    assert r.last_hits[0][1]["id"] == "host.storage.capacity.disk-full"


def test_numeric_selection_runs_that_skill(monkeypatch):
    r = repl.Repl()
    r._handle("kafka 积压")
    picked = {}
    monkeypatch.setattr(r, "_run", lambda sid, resume=False: picked.setdefault("id", sid))
    r._handle("1")
    assert picked["id"] == r.last_hits[0][1]["id"]


def test_numeric_without_hits_is_safe(capsys):
    r = repl.Repl()
    r._handle("2")            # 无候选
    assert "先描述问题" in capsys.readouterr().out


def test_quit_stops_loop():
    r = repl.Repl()
    r._handle("quit")
    assert r.running is False


def test_builtins_dont_crash(capsys):
    r = repl.Repl()
    r._handle("help")
    r._handle("list host")
    r._handle("info host.storage.capacity.disk-full")
    r._handle("info nonexistent.skill")
    out = capsys.readouterr().out
    assert "用法" in out and "决策树" in out and "没有这个 Skill" in out


def test_no_tty_refuses(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    rc = repl.start()
    assert rc == 2
    assert "需要终端" in capsys.readouterr().err
