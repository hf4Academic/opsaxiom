"""T-1 运行时导航档会话测试（脚本驱动，非交互）。"""
import os
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import runtime  # noqa: E402


def _run_demo(demo_file, skill_id, tmp_home):
    a = yaml.safe_load((ROOT / "demos" / demo_file).read_text())
    p = next(x for x in (ROOT / "skills").rglob("skill.yaml")
             if yaml.safe_load(x.read_text())["metadata"]["id"] == skill_id)
    os.environ["OPSAXIOM_HOME"] = str(tmp_home)
    io = runtime.IO(answers=a.get("answers"), echo=False)
    sess = runtime.Session(p, params=a.get("params"), mode=a.get("mode", "guided"), io=io, sid="t")
    return sess.run()


def test_disk_full_guided_reaches_done(tmp_path):
    r = _run_demo("disk-full-guided.answers.yaml", "host.storage.capacity.disk-full", tmp_path)
    assert r["outcome"] == "done"
    assert r["path"][-1] == "done_ok"
    # 审计落盘且含 action 审批记录
    audit = pathlib.Path(r["audit_file"]).read_text().splitlines()
    assert any('"type": "action"' in ln and '"approved": true' in ln for ln in audit)


def test_mysql_slow_query_guided_reaches_lock_exit(tmp_path):
    r = _run_demo("mysql-slow-query-guided.answers.yaml", "middleware.mysql.slow-query", tmp_path)
    assert r["outcome"] == "done"
    assert r["path"][-1] == "lock_exit"


def test_render_template():
    from runtime import render
    ctx = {"mount": "/data", "sid": "s1", "rows": [{"pcent": 80, "comm": "java"}], "output": {"v": 3}}
    assert render("使用率 {{rows[0].pcent}}% 于 {{mount}}", ctx) == "使用率 80% 于 /data"
    assert render("会话 {{sid}}", ctx) == "会话 s1"
    assert render("进程 {{rows[0].comm}}", ctx) == "进程 java"
    # 求值失败保留原样，不崩
    assert render("坏 {{nonexistent[9].x}}", ctx) == "坏 "  # 缺失→空串
