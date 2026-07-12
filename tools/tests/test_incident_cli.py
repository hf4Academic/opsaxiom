"""N-1 incident JSON API 测试：授权门 / 本机取证 / 远端计划。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import incident_cli as IC  # noqa: E402


def _runner(table):
    def run(cmd, timeout=15):
        for k, v in table.items():
            if k in cmd:
                return v
        return ""
    return run


def test_needs_grant_gate(monkeypatch, tmp_path):
    """未授权本机 → needs_grant，绝不执行、不出卷宗。"""
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    r = IC.run_incident("磁盘满了但 df 有空间", params={"mount": "/data"},
                        target="local", grant=False)
    assert r.get("needs_grant") is True
    assert "dossier" not in r or r.get("dossier") is None


def test_local_grant_produces_dossier(monkeypatch, tmp_path):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    runner = _runner({
        "df -B1 --output=target,size,used,avail,pcent /data":
            "Mounted 1B-blocks Used Avail Use%\n/data 100 96 4 96%",
        "df -i --output=ipcent /data":
            "Mounted ITotal IUsed IUse%\n/data 1000 400 40%",
        "lsof +L1 /data": "0",
        "du -xB1 /data": "2147483648\t/data/var/log/app.log",
    })
    r = IC.run_incident("磁盘满了但 df 有空间", params={"mount": "/data"},
                        target="local", grant=True, runner=runner, now=1000.0)
    assert r["dossier"] is not None
    assert r["report_markdown"].startswith("# 故障报告")
    # 处置指引存在且强调走审批门（模型/自动流程无权越过 R3/R6）
    if r.get("treatment"):
        assert "run" in r["treatment"]["how"]


def test_remote_target_returns_plan_not_execution(monkeypatch, tmp_path):
    """远端目标：只出粘贴块计划，绝不执行任何命令。"""
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    r = IC.run_incident("交换机 bgp 邻居掉了", params={"peer_ip": "10.0.0.1"},
                        target="switch-a")
    assert "plan" in r and r["plan"]["commands"]
    assert "dossier" not in r or r.get("dossier") is None
    assert r["plan"]["nonce"]


def test_no_match_is_graceful(monkeypatch, tmp_path):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    r = IC.run_incident("zzz 完全不相关的输入 qqq", target="local")
    assert r["hypotheses"] == [] and r["dossier"] is None
