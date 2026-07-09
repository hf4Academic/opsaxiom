"""P-4 maturity 流水线测试（非破坏性：只读断言，不改动仓库 Skill）。"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import promote  # noqa: E402


def test_promote_disk_full_passes():
    # disk-full 已具备 sim 证据+rollback 往返，promote 返回 0（幂等，保持 sim_verified）
    rc = promote.promote(ROOT / "skills/host/disk-full/skill.yaml")
    assert rc == 0


def test_promote_rejects_without_rollback_evidence():
    # load-high 无 rollback_assert 测试 → S8 不过，拒绝晋级
    rc = promote.promote(ROOT / "skills/host/load-high/skill.yaml")
    assert rc == 1


def test_scenarios_lookup():
    scens = promote._scenarios_for(ROOT / "skills/host/disk-full/skill.yaml")
    assert len(scens) == 3
