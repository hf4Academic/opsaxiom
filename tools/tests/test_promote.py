"""P-4/P-5 maturity 流水线测试（非破坏性：只断言 reject 路径与场景查找，不改动仓库 Skill）。

promote 的成功路径会写文件，故不在单测里跑（已在 P-5 批量晋级中实测）；
这里只测"会在写盘前返回"的拒绝分支与场景查找。
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import promote  # noqa: E402


def test_promote_rejects_when_no_scenario():
    # raid-degraded 是纯诊断且没有 sim 场景 → 在写盘前因"无场景"拒绝(rc=1)，不改动文件
    path = ROOT / "skills/host/raid-degraded/skill.yaml"
    before = path.read_text()
    rc = promote.promote(path)
    assert rc == 1
    assert path.read_text() == before            # 未被改动


def test_scenarios_lookup():
    # 3 个 context_walk + 1 个 real（F-9 修复后恢复）
    assert len(promote._scenarios_for(ROOT / "skills/host/disk-full/skill.yaml")) == 4
    assert promote._scenarios_for(ROOT / "skills/host/raid-degraded/skill.yaml") == []
    assert len(promote._scenarios_for(ROOT / "skills/host/agent-deploy/skill.yaml")) == 1
    # load-high 现有 context + real 两个场景
    assert len(promote._scenarios_for(ROOT / "skills/host/load-high/skill.yaml")) == 2
