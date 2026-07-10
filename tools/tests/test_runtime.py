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
    # 审计落盘且含 action 审批记录（U-1：decision + verify 结果 + 输出摘要）
    audit = pathlib.Path(r["audit_file"]).read_text().splitlines()
    assert any('"type": "action"' in ln and '"decision": "proceed"' in ln for ln in audit)
    assert any('"verify_passed": true' in ln for ln in audit)
    assert any('"output":' in ln for ln in audit)


def test_action_skip_and_quit(tmp_path):
    """U-1：action 三选项——skip 走 goto 继续，quit 中断并存续跑状态。"""
    os.environ["OPSAXIOM_HOME"] = str(tmp_path)
    a = yaml.safe_load((ROOT / "demos" / "disk-full-guided.answers.yaml").read_text())
    p = next(x for x in (ROOT / "skills").rglob("skill.yaml")
             if yaml.safe_load(x.read_text())["metadata"]["id"] == "host.storage.capacity.disk-full")
    # quit：在 action 节点退出，state 应指向该 action 节点
    a["answers"]["compress_old_logs"] = "quit"
    io = runtime.IO(answers=a["answers"], echo=False)
    sess = runtime.Session(p, params=a["params"], mode="guided", io=io, sid="q")
    r = sess.run()
    assert r["outcome"] == "quit"
    state = tmp_path / "sessions" / "q.state.json"
    assert state.exists()
    import json
    assert json.loads(state.read_text())["node"] == "compress_old_logs"
    # resume：换成 proceed，从 action 续跑到 done
    a["answers"]["compress_old_logs"] = "y"
    io2 = runtime.IO(answers=a["answers"], echo=False)
    sess2 = runtime.Session(p, params=a["params"], mode="guided", io=io2, sid="q")
    start = sess2.load_state()
    assert start == "compress_old_logs"
    r2 = sess2.run(start=start)
    assert r2["outcome"] == "done"
    assert not state.exists()          # 完成后清理续跑状态


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
    # 求值失败（语法不可解析）保留原样，不崩
    assert render("坏 {{1 + }}", ctx) == "坏 {{1 + }}"
    # U-1：字段缺失但求值成功→None→⟨?⟩ 占位，不留语义黑洞
    assert render("共 {{gone}} 个", ctx) == "共 ⟨?⟩ 个"
    assert render("坏 {{nonexistent[9].x}}", ctx) == "坏 ⟨?⟩"
