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


import yaml as _yaml  # noqa: E402
_CTX_SCENARIOS = [s for s in SCENARIOS if _yaml.safe_load(s.read_text()).get("mode") != "real"]
_REAL_SCENARIOS = [s for s in SCENARIOS if _yaml.safe_load(s.read_text()).get("mode") == "real"]


@pytest.mark.parametrize("scenario", _CTX_SCENARIOS, ids=lambda p: p.stem)
def test_scenario_path(scenario):
    sc = _yaml.safe_load(scenario.read_text())
    r = run_sim.run(ROOT / sc["skill"], scenario)
    assert r["path_ok"], f"路径不匹配\n实际: {r['path']}\n期望: {r['expect']}"
    if r["rollback_ok"] is not None:
        assert r["rollback_ok"], f"回滚往返失败: {r['notes']}"


@pytest.mark.parametrize("scenario", _REAL_SCENARIOS, ids=lambda p: p.stem)
def test_scenario_real(scenario):
    import shutil
    sc = _yaml.safe_load(scenario.read_text())
    # X-2：声明依赖的外部工具（如 kubectl）不在环境里就跳过，不失败
    for tool in sc.get("requires", []):
        if shutil.which(tool) is None:
            pytest.skip(f"缺 {tool}，跳过真实场景 {scenario.stem}")
    r = run_sim.run(ROOT / sc["skill"], scenario)
    assert r["completed"], f"真实模式未终止: {r['path']}"
    assert r["evidence"] == "real_roundtrip"


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


def test_real_mode_runs_end_to_end():
    """真实模式在本机跑通纯诊断 Skill，产出 real_roundtrip 证据且终止。"""
    import yaml
    for name in ["real-load-high", "real-swap-thrash"]:
        sc = ROOT / "sim" / "scenarios" / f"{name}.yaml"
        d = yaml.safe_load(sc.read_text())
        r = run_sim.run(ROOT / d["skill"], sc)
        assert r["completed"], f"{name} 未跑到终止: {r['path']}"
        assert r["evidence"] == "real_roundtrip"


def test_kubectl_readonly_gating():
    """X-2：kubectl 只读动词放行，写动词(尤其 exec)一律拒。"""
    ro = ["kubectl -n default get pod nginx -o json", "kubectl -n ns describe pod x",
          "kubectl -n ns logs x --previous --tail=50", "kubectl top pod"]
    wr = ["kubectl -n ns delete pod x", "kubectl apply -f x.yaml",
          "kubectl exec x -- rm -rf /", "kubectl rollout undo deploy/x",
          "kubectl scale deploy/x --replicas=3"]
    for c in ro:
        assert run_sim._is_readonly(c), c
    for c in wr:
        assert not run_sim._is_readonly(c), c


def test_f16_kubectl_shell_injection_rejected():
    """F-16（八轮评审）：shell 元字符注入一律拒——只读 kubectl 不需要 ;|&$()<>` 。"""
    inj = ["kubectl get pods; rm -rf /", "kubectl -n ns get pod `rm -rf /`",
           "kubectl get pod $(reboot)", "kubectl get pod | sh", "kubectl get pod > /etc/x"]
    for c in inj:
        assert not run_sim._is_readonly(c), c


# ---- H-7：三种补齐的回滚往返 mock（service_restore / snapshot / transaction）----

SVCBIN = ROOT / "tools" / "bin" / "opsaxiom-svcstate"
FSBIN = ROOT / "tools" / "bin" / "opsaxiom-fsnapshot"
TXBIN = ROOT / "tools" / "bin" / "opsaxiom-txn"


def test_svcstate_restart_restore_roundtrip():
    """service_restore：restart 改变状态，restore 精确回到动作前状态。"""
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, OPSAXIOM_SVCSTATE_ROOT=td, OPSAXIOM_SVCSTATE_INIT="failed")
        def run(*a):
            return subprocess.run([sys.executable, str(SVCBIN), *a],
                                  env=env, capture_output=True, text=True)
        run("restart", "u.service")
        assert run("get", "u.service").stdout.strip() == "active"
        run("restore", "u.service")
        assert run("get", "u.service").stdout.strip() == "failed"
        # 幂等：无 before 时 restore 不应改变状态
        run("restore", "u.service")
        assert run("get", "u.service").stdout.strip() == "failed"


def test_fsnapshot_snap_mutate_restore_roundtrip():
    """snapshot：快照→改动→restore 逐字节还原；无快照 restore 退出码 1。"""
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, OPSAXIOM_FSNAPSHOT_ROOT=str(pathlib.Path(td) / "s"))
        f = pathlib.Path(td) / "vol.img"
        f.write_text("original")
        def run(*a, check=True):
            return subprocess.run([sys.executable, str(FSBIN), *a],
                                  env=env, capture_output=True, check=check)
        run("snap", str(f))
        f.write_text("mutated")
        run("restore", str(f))
        assert f.read_text() == "original"
        # 无快照的文件 restore 必须失败而非静默
        g = pathlib.Path(td) / "no-snap.img"
        g.write_text("x")
        r = run("restore", str(g), check=False)
        assert r.returncode == 1


def test_txn_begin_revert_and_confirm():
    """transaction：begin 切修订，revert 精确回退；confirm 后 revert 不再回退。"""
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, OPSAXIOM_TXN_ROOT=td, OPSAXIOM_TXN_INIT="5")
        def run(*a):
            return subprocess.run([sys.executable, str(TXBIN), *a],
                                  env=env, capture_output=True, text=True)
        run("begin", "d", "3")
        assert run("get", "d").stdout.strip() == "3"
        run("revert", "d")
        assert run("get", "d").stdout.strip() == "5"
        # 确认后 before 被丢弃，revert 保持当前修订（事务已提交）
        run("begin", "d", "2")
        run("confirm", "d")
        run("revert", "d")
        assert run("get", "d").stdout.strip() == "2"
