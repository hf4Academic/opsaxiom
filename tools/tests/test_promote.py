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
    # 造一个 ROOT 内的临时合法 Skill（无 sim 场景）→ 写盘前因"无场景"拒绝(rc=1)、不改动文件。
    # （H-1 后库内 draft 大多已补场景，故用临时 Skill 而非依赖某库内 Skill 的缺场景状态。
    #  _scenarios_for 用 relative_to(ROOT)，必须落在 ROOT 内。）
    import shutil

    import yaml
    src = ROOT / "skills/host/raid-degraded/skill.yaml"
    skill = yaml.safe_load(src.read_text())
    skill["metadata"]["id"] = "host.storage.__promote_notest__"
    d = ROOT / "skills" / "host" / "__promote_notest__"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "skill.yaml"
    path.write_text(yaml.safe_dump(skill, allow_unicode=True))
    try:
        before = path.read_text()
        rc = promote.promote(path)          # 无场景指向它 → 拒绝
        assert rc == 1
        assert path.read_text() == before   # 未被改动
    finally:
        shutil.rmtree(d)


def test_scenarios_lookup():
    # disk-full：3 个 context_walk + 1 个 real（F-9 修复后恢复）
    assert len(promote._scenarios_for(ROOT / "skills/host/disk-full/skill.yaml")) == 4
    # 无场景指向的 ROOT 内虚构路径 → 空（文件不存在也能 resolve + relative_to）
    assert promote._scenarios_for(ROOT / "skills/host/__no_such_skill__/skill.yaml") == []
    assert len(promote._scenarios_for(ROOT / "skills/host/agent-deploy/skill.yaml")) == 1
    # load-high 现有 context + real 两个场景
    assert len(promote._scenarios_for(ROOT / "skills/host/load-high/skill.yaml")) == 2
