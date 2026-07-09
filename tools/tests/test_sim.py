"""O-6 仿真执行器 + opsaxiom-quarantine 集成测试。"""
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sim"))
import run_sim  # noqa: E402

SCENARIOS = sorted((ROOT / "sim" / "scenarios").glob("*.yaml"))


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_path(scenario):
    import yaml
    sc = yaml.safe_load(scenario.read_text())
    r = run_sim.run(ROOT / sc["skill"], scenario)
    assert r["path_ok"], f"路径不匹配\n实际: {r['path']}\n期望: {r['expect']}"
    if r["rollback_ok"] is not None:
        assert r["rollback_ok"], f"回滚往返失败: {r['notes']}"


QBIN = ROOT / "tools" / "bin" / "opsaxiom-quarantine"


def test_quarantine_move_restore_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        qroot = pathlib.Path(td) / "q"
        f = pathlib.Path(td) / "victim.log"
        f.write_text("important")
        env = dict(os.environ, OPSAXIOM_QUARANTINE_ROOT=str(qroot))

        subprocess.run([sys.executable, str(QBIN), "move", "--session", "t", str(f)],
                       check=True, env=env, capture_output=True)
        assert not f.exists()                      # 已移走

        subprocess.run([sys.executable, str(QBIN), "restore", "--session", "t"],
                       check=True, env=env, capture_output=True)
        assert f.exists() and f.read_text() == "important"   # 精确还原


def test_quarantine_purge_requires_confirmation():
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, OPSAXIOM_QUARANTINE_ROOT=str(pathlib.Path(td) / "q"))
        # 不加 --yes 应拒绝（退出码 2）
        r = subprocess.run([sys.executable, str(QBIN), "purge", "--session", "t"],
                           env=env, capture_output=True)
        assert r.returncode == 2


DBIN = ROOT / "tools" / "bin" / "opsaxiom-deploy"


def test_deploy_idempotent_and_uninstall():
    import tempfile, os, subprocess, sys
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, OPSAXIOM_DEPLOY_ROOT=td)
        run = lambda *a: subprocess.run([sys.executable, str(DBIN), *a], env=env, capture_output=True, text=True)
        # 首次安装
        r1 = run("node_exporter", "--arch", "amd64", "--port", "9100")
        assert r1.returncode == 0 and "已部署" in r1.stdout
        assert (pathlib.Path(td) / "state" / "node_exporter.json").exists()
        # 幂等：再装一次跳过
        r2 = run("node_exporter", "--arch", "amd64", "--port", "9100")
        assert "幂等跳过" in r2.stdout
        # 卸载回到干净
        r3 = run("node_exporter", "--uninstall")
        assert r3.returncode == 0
        assert not (pathlib.Path(td) / "state" / "node_exporter.json").exists()
        assert not (pathlib.Path(td) / "bin" / "node_exporter").exists()
        # 卸载幂等
        r4 = run("node_exporter", "--uninstall")
        assert "无需卸载" in r4.stdout


def test_deploy_checksum_gate():
    import tempfile, os, subprocess, sys
    with tempfile.TemporaryDirectory() as td:
        fake = pathlib.Path(td) / "binary"
        fake.write_bytes(b"real-binary-content")
        env = dict(os.environ, OPSAXIOM_DEPLOY_ROOT=str(pathlib.Path(td) / "root"))
        r = subprocess.run([sys.executable, str(DBIN), "probe", "--binary", str(fake),
                            "--sha256", "deadbeef"], env=env, capture_output=True, text=True)
        assert r.returncode == 3 and "checksum 不匹配" in r.stderr   # 篡改/错误校验和被拦
