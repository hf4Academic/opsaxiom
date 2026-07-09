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
