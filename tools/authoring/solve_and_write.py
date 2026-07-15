"""对给定 skill.yaml 求解 context_walk 场景、写盘、run_sim 验证。成功返回场景路径。"""
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import run_sim  # noqa: E402
import scenario_solver as S  # noqa: E402

SCEN = ROOT / "sim" / "scenarios"


def solve_write_verify(skill_path, base_ctx=None, name=None):
    skill_path = pathlib.Path(skill_path)
    if not skill_path.is_absolute():
        skill_path = (ROOT / skill_path).resolve()
    skill = yaml.safe_load(skill_path.read_text(encoding="utf-8"))
    sol = S.solve(skill, base_ctx=base_ctx)
    if not sol:
        return None, "求解失败（表达式形态超出启发式）"
    node_ctx, answers, path = sol
    sid = skill["metadata"]["id"]
    name = name or (sid.replace(".", "-") + "-auto")
    scen = {"skill": str(skill_path.relative_to(ROOT)),
            "scenario": f"{sid} 自动求解走查",
            "expect_path": path, "node_ctx": node_ctx}
    if answers:
        scen["answers"] = answers
    if base_ctx:
        scen["base_ctx"] = base_ctx
    scen_path = SCEN / f"{name}.yaml"
    scen_path.write_text(yaml.safe_dump(scen, allow_unicode=True, sort_keys=False),
                         encoding="utf-8")
    r = run_sim.run(skill_path, scen_path)
    if r.get("path_ok"):
        return scen_path, "ok"
    scen_path.unlink(missing_ok=True)
    return None, f"sim 未过：走了 {r.get('path')} 期望 {path}"


if __name__ == "__main__":
    p, msg = solve_write_verify(sys.argv[1])
    print(("✔ " + str(p)) if p else ("✘ " + msg))
    sys.exit(0 if p else 1)
