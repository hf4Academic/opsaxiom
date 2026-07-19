"""I-7 混合取证端到端：本机 + 已授权远程自动执行，未授权/不可达降级粘贴。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import evidence  # noqa: E402
import incident as I  # noqa: E402
import sweep  # noqa: E402
from facts import LOCAL, FactStore  # noqa: E402


def _skill(taxonomy="host/cpu/x"):
    return {
        "metadata": {"id": "test.host.x", "name": "t", "taxonomy": taxonomy,
                     "maturity": "sim_verified"},
        "tree": {"entry": "c1", "nodes": [
            {"id": "c1", "type": "check", "title": "查负载",
             "run": {"linux": "cat /proc/loadavg"},
             "branch": [{"when": "output.value > 0", "goto": "done"}],
             "otherwise": "done"},
            {"id": "done", "type": "done", "summary": "完"},
        ]},
    }


def _plan_for(target):
    return evidence.build_plan([(_skill(), {})], target=target)


def test_mixed_local_and_authorized_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    # 组合两个 plan：本机 + 已授权远程 web-01
    store = FactStore()
    plan_local = _plan_for(LOCAL)
    plan_remote = _plan_for("web-01")
    plan = {"target": "mixed", "waves": plan_local["waves"] + plan_remote["waves"]}
    authorized = lambda n: n == "web-01"
    remote_runner = lambda tn, cmd, pr: f"remote:{tn}:{cmd}"
    local_runner = lambda cmd: f"local:{cmd}"
    res = sweep.execute_mixed(plan, {}, store, now="T",
                              local_runner=local_runner,
                              remote_runner=remote_runner,
                              authorized=authorized)
    targets = {r.get("target") for r in res["executed"]}
    assert LOCAL in targets and "web-01" in targets       # 两者都自动执行
    assert res["manual"] == {}                            # 无降级


def test_unauthorized_remote_degrades_to_manual(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    store = FactStore()
    plan = _plan_for("web-02")
    authorized = lambda n: False                            # web-02 未授权
    res = sweep.execute_mixed(plan, {}, store, now="T",
                              local_runner=lambda c: "x",
                              remote_runner=lambda tn, c, p: "y",
                              authorized=authorized)
    assert res["executed"] == []                            # 没自动执行
    assert "web-02" in res["manual"]                        # 降级为粘贴目标


def test_classify_target():
    from facts import LOCAL as L
    assert sweep.classify_target(L)[0] == "local"
    assert sweep.classify_target("t", authorized=lambda n: False)[0] == "paste"
    assert sweep.classify_target("t", authorized=lambda n: True)[0] == "auto"
    assert sweep.classify_target("t", authorized=lambda n: True,
                                 reachable=lambda n: False)[0] == "paste"   # 拨不通


def test_incident_mixed_sweep_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    inc = I.Incident("机器卡")
    inc.add_hypotheses([_skill()])
    # incident target 是 LOCAL，远程混合由调用方拼 plan；此处验证端点存在且跑通
    res = inc.mixed_sweep(now="T", authorized=lambda n: False)
    assert "executed" in res and "manual" in res
