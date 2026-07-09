#!/usr/bin/env python3
"""
maturity 流水线（P-4）—— 唯一被授权写 metadata.maturity 的工具（docs/03：maturity 由流水线写入）。

promote <skill.yaml>            依据校验 + 仿真证据晋级到 sim_verified
demote  <skill.yaml> <reason>   降级回 draft 并记录原因

晋级 sim_verified 的门槛（docs/05 §1 + S8）：
  1. 校验器零 ERROR；
  2. 该 Skill 至少一个可执行 sim 场景通过（sim/scenarios/*.yaml 中 skill 指向它）；
  3. 若该 Skill 的 tests 有 rollback_assert，则须有场景实际通过回滚往返；
  4. tests 非空且至少一个 rollback_assert（S8）。

写法：只文本替换 `maturity:` 一行（保留注释/格式），证据写入 <skill_dir>/.maturity/。
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim"))
import yaml            # noqa: E402
import validate as V   # noqa: E402
import run_sim         # noqa: E402

SCEN_DIR = ROOT / "sim" / "scenarios"


def _scenarios_for(skill_path):
    skill_rel = str(skill_path.resolve().relative_to(ROOT))
    out = []
    for sc in sorted(SCEN_DIR.glob("*.yaml")):
        data = yaml.safe_load(sc.read_text())
        if data.get("skill") == skill_rel:
            out.append(sc)
    return out


def _maturity_line_replace(path, new):
    raw = path.read_text(encoding="utf-8")
    new_raw, n = re.subn(r"(?m)^(\s*maturity:\s*)\S+", rf"\g<1>{new}", raw, count=1)
    if n != 1:
        raise RuntimeError("未找到唯一的 maturity 行")
    path.write_text(new_raw, encoding="utf-8")


def _evidence_dir(skill_path):
    d = skill_path.parent / ".maturity"
    d.mkdir(exist_ok=True)
    return d


def promote(skill_path):
    skill_path = pathlib.Path(skill_path).resolve()
    skill = yaml.safe_load(skill_path.read_text())
    name = skill["metadata"]["id"]

    # 1. 校验零 ERROR
    rep = V.validate_file(skill_path, V._default_validator())
    if rep.errors:
        print(f"✘ 校验未过，拒绝晋级：{[e[2] for e in rep.errors]}")
        return 1

    # 4. S8（含 action 才要求 rollback_assert；纯诊断路径覆盖即可，见 R-6）
    tests = skill.get("tests", [])
    nodes = skill.get("tree", {}).get("nodes", [])
    has_action = any(n.get("type") == "action" for n in nodes)
    if not tests:
        print("✘ S8 未满足：tests 为空")
        return 1
    if has_action and not any(t.get("rollback_assert") for t in tests):
        print("✘ S8 未满足：含 action 的 Skill 须有 rollback_assert 测试")
        return 1

    # 2/3. 仿真证据
    scens = _scenarios_for(skill_path)
    if not scens:
        print("✘ 无可执行 sim 场景（sim/scenarios/ 下没有指向该 Skill 的场景）")
        return 1
    results, rollback_seen = [], False
    for sc in scens:
        r = run_sim.run(skill_path, sc)
        ok = r["path_ok"] and (r["rollback_ok"] is not False)
        results.append({"scenario": sc.name, "path_ok": r["path_ok"], "rollback_ok": r["rollback_ok"]})
        if r["rollback_ok"] is True:
            rollback_seen = True
        if not ok:
            print(f"✘ 场景 {sc.name} 未通过：{r['path']} vs {r['expect']}")
            return 1
    if has_action and any(t.get("rollback_assert") for t in tests) and not rollback_seen:
        print("✘ 该 Skill 声明了 rollback_assert，但没有场景实际验证回滚往返")
        return 1

    # 通过 → 晋级
    prev = skill["metadata"]["maturity"]
    _maturity_line_replace(skill_path, "sim_verified")
    ev = {
        "skill": name, "action": "promote", "from": prev, "to": "sim_verified",
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "validator": "0 ERROR", "scenarios": results,
    }
    (_evidence_dir(skill_path) / "promote.json").write_text(
        json.dumps(ev, ensure_ascii=False, indent=2))
    print(f"✔ {name}: {prev} → sim_verified（{len(scens)} 个场景通过，回滚往返={'有' if rollback_seen else '无'}）")
    return 0


def demote(skill_path, reason):
    skill_path = pathlib.Path(skill_path).resolve()
    skill = yaml.safe_load(skill_path.read_text())
    prev = skill["metadata"]["maturity"]
    _maturity_line_replace(skill_path, "draft")
    ev = {
        "skill": skill["metadata"]["id"], "action": "demote", "from": prev, "to": "draft",
        "at": datetime.datetime.now().isoformat(timespec="seconds"), "reason": reason,
    }
    (_evidence_dir(skill_path) / "demote.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2))
    print(f"✔ {skill['metadata']['id']}: {prev} → draft（原因：{reason}）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("promote"); sp.add_argument("skill")
    sd = sub.add_parser("demote"); sd.add_argument("skill"); sd.add_argument("reason")
    args = ap.parse_args()
    return promote(args.skill) if args.cmd == "promote" else demote(args.skill, args.reason)


if __name__ == "__main__":
    sys.exit(main())
