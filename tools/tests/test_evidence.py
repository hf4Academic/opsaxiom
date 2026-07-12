"""Z-2 检查前沿提取与取证计划测试：三种树形态 + 多假设去重 + auto 判定 + 波次。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import evidence as E  # noqa: E402


def _load(rel):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


# ---- 形态一：disk-full（本机、模板依赖 alert 参数 mount，单波全自动）----
def test_disk_full_single_wave_all_auto():
    df = _load("skills/host/disk-full/skill.yaml")
    plan = E.build_plan([(df, {"mount": "/data"})])
    assert len(plan["waves"]) == 1                    # 命令只引用 alert 参数 → 单波
    assert plan["manual_count"] == 0                  # 全是 linux 只读 → 全自动
    cmds = E.plan_commands(plan)
    assert plan["auto_count"] == len(cmds)
    # 参数已渲染进命令（不再留 {{mount}}）
    assert any("/data" in c and "{{" not in c for c in cmds)
    assert any(c.startswith("lsof") for c in cmds)    # 各分支只读检查都进了前沿


# ---- 形态二：xid-error（本机、dmesg|grep 管道判为只读、单命令）----
def test_xid_error_pipe_is_auto():
    xid = _load("skills/aicomp/xid-error/skill.yaml")
    plan = E.build_plan([(xid, {})])
    cmds = E.plan_commands(plan)
    assert plan["auto_count"] == len(cmds) >= 1
    assert any("dmesg" in c for c in cmds)            # 管道命令纳入且自动


# ---- 形态三：bgp（网络设备目标、show 命令不在 linux 白名单 → 纳入但不自动）----
def test_bgp_device_manual_not_auto():
    bgp = _load("skills/network/bgp-neighbor-down/skill.yaml")
    plan = E.build_plan([(bgp, {"peer_ip": "10.0.0.1"})], target="switch-a")
    assert plan["auto_count"] == 0                    # 设备目标：一律不自动执行
    assert plan["manual_count"] >= 1                  # 但 show 命令要纳入粘贴块
    cmds = E.plan_commands(plan)
    assert any("show ip bgp" in c for c in cmds)
    assert any("10.0.0.1" in c for c in cmds)         # peer_ip 已渲染
    # 依赖未知派生量的检查被诚实排除（intf/update_source 未提供）
    assert not any("{{" in c for c in cmds)


def test_unrenderable_checks_excluded():
    """不可渲染（依赖未知参数）的检查不进计划——诚实，不硬凑。"""
    bgp = _load("skills/network/bgp-neighbor-down/skill.yaml")
    # 不给 peer_ip → 连 peer_state 都不可渲染
    plan = E.build_plan([(bgp, {})], target="switch-a")
    cmds = E.plan_commands(plan)
    assert all("{{" not in c for c in cmds)           # 计划里没有半渲染命令
    assert not any("neighbors" in c for c in cmds)    # 需 peer_ip 的检查被排除


# ---- 多假设合并去重（省回合的核心）----
def _mini(skill_id, cmd):
    return {"metadata": {"id": skill_id},
            "tree": {"entry": "c1",
                     "nodes": [{"id": "c1", "type": "check",
                                "run": {"linux": cmd},
                                "branch": [{"when": "true", "goto": "done"}],
                                "otherwise": "done"},
                               {"id": "done", "type": "done"}]}}


def test_multi_hypothesis_dedup_merges_provenance():
    """两个假设共享同一条 df → 只采一次，for_skills 记录两个假设。"""
    a = _mini("host.a", "df -h /data")
    b = _mini("host.b", "df -h /data")
    plan = E.build_plan([(a, {}), (b, {})])
    probes = [p for w in plan["waves"] for p in w["probes"]]
    assert len(probes) == 1                            # 去重成一条
    assert set(probes[0]["for_skills"]) == {"host.a", "host.b"}


def test_normalized_command_dedup():
    """空白差异归一后同命令去重（df -h  /data == df -h /data）。"""
    a = _mini("host.a", "df -h /data")
    b = _mini("host.b", "df -h    /data")
    plan = E.build_plan([(a, {}), (b, {})])
    probes = [p for w in plan["waves"] for p in w["probes"]]
    assert len(probes) == 1
