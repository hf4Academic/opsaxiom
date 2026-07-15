"""
批量 skill 生成器（H-gen）——吃紧凑 spec 出 skill.yaml + 自动求解 sim 场景 + 晋级。

一个 spec 是一个 dict（见 SPEC_SCHEMA 注释），领域内容（命令/判据/结论/cautions）由
作者按领域知识填；生成器只负责把它编译成合规 skill.yaml，并调 scenario_solver 求场景。
保证 Fable 的树规模下限：≥2 个 check、≥3 个终点。不满足直接报错，不生成"伪 Skill"。

spec = {
  id, name, taxonomy, symptom,           # 元信息
  platform: "linux"|"cisco_ios"|...,     # run 的连接器键（默认 linux）
  checks: [                              # ≥2
    {id, title, cmd, parser?,            # parser 省略=generic 兜底由作者在 branch 里注意
     branches: [{when, goto}], otherwise, cautions:[...]}
  ],
  dones: [{id, summary}],                # 结论节点
  # escalate 自动补（若 checks 里 goto 到 escalate）
}
"""
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import solve_and_write  # noqa: E402
import validate as V    # noqa: E402


def _skill_from_spec(spec):
    plat = spec.get("platform", "linux")
    cap = spec.get("capability_level", "read")
    net = spec.get("network", False)       # True → 网络设备 skill（多平台 run + device 元信息）
    nodes = []
    for c in spec["checks"]:
        # 多平台命令：check 用 cmds={cisco_ios:..,huawei_vrp:..} 或单平台 cmd
        run = c["cmds"] if c.get("cmds") else {plat: c["cmd"]}
        node = {"id": c["id"], "type": "check", "title": c["title"], "run": run}
        if c.get("parser"):
            node["parser"] = c["parser"]
        node["branch"] = [{"when": b["when"], "goto": b["goto"]} for b in c["branches"]]
        node["otherwise"] = c.get("otherwise", "escalate")
        if c.get("cautions"):
            node["cautions"] = c["cautions"]
        nodes.append(node)
    for d in spec["dones"]:
        nodes.append({"id": d["id"], "type": "done", "summary": d["summary"]})
    # escalate 节点：若任何 goto/otherwise 指向 escalate 且未显式定义，补一个
    referenced = {b["goto"] for c in spec["checks"] for b in c["branches"]}
    referenced |= {c.get("otherwise", "escalate") for c in spec["checks"]}
    ids = {n["id"] for n in nodes}
    if "escalate" in referenced and "escalate" not in ids:
        nodes.append({"id": "escalate", "type": "escalate",
                      "summary": spec.get("escalate_summary",
                                          "打包升级：已采集的事实与走过的路径。")})
    entry = spec["checks"][0]["id"]
    skill = {
        "apiVersion": "skill/v0.1", "kind": "Diagnostic",
        "metadata": {
            "id": spec["id"], "name": spec["name"], "taxonomy": spec["taxonomy"],
            "version": "0.1.0", "maturity": "draft",
            "platforms": ([{"device": d} for d in spec.get("devices", ["cisco_ios"])]
                          if net else [{"os": "linux"}]),
            "authors": ["opsagent-core"], "license": "Apache-2.0",
            "provenance": {"generated_by": "claude-opus-4-8",
                           "reviewed_by": ["claude-fable-5"]},
            "expires_review": "2027-07-01"},
        "requirements": {"capability_level": cap,
                         "connectors": [spec.get("connector", "netconf" if net else "ssh")],
                         "facts": spec.get("facts", ["os.family"])},
        "tree": {"entry": entry, "nodes": nodes},
        "tests": [],                       # 由求解器 + skill.tests 声明补
        "feedback": {"ask": spec.get("feedback", f"{spec['name']}定位了吗？")},
    }
    return skill


def _check_tree_floor(skill):
    """Fable 红线：≥2 check、≥3 终点(done/escalate)。不满足 → 报错，不生成伪 Skill。"""
    nodes = skill["tree"]["nodes"]
    checks = sum(1 for n in nodes if n["type"] == "check")
    terms = sum(1 for n in nodes if n["type"] in ("done", "escalate"))
    if checks < 2:
        raise ValueError(f"{skill['metadata']['id']}: check 数 {checks} < 2（红线）")
    if terms < 3:
        raise ValueError(f"{skill['metadata']['id']}: 终点数 {terms} < 3（红线）")


def generate(spec, promote=True):
    """spec → skill.yaml 落盘 → 求解场景 → （可选）晋级。返回 (skill_path, status)。"""
    skill = _skill_from_spec(spec)
    _check_tree_floor(skill)
    # 落盘：skills/<l1>/<leaf>/skill.yaml
    l1 = spec["taxonomy"].split("/")[0]
    leaf = spec["taxonomy"].split("/")[-1]
    d = ROOT / "skills" / l1 / leaf
    d.mkdir(parents=True, exist_ok=True)
    skill_path = d / "skill.yaml"
    skill_path.write_text(yaml.safe_dump(skill, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
    # 校验
    rep = V.validate_file(skill_path, V._default_validator())
    if rep.errors:
        return skill_path, f"✘ 校验 {[e[2] for e in rep.errors][:3]}"
    # 求解场景（写进 skill.tests 一并声明，run_sim 验证）
    scen, msg = solve_and_write.solve_write_verify(skill_path)
    if not scen:
        return skill_path, f"✘ 场景求解 {msg}"
    # 把求解出的场景登记进 skill.tests（S8 需 tests 非空）
    sc = yaml.safe_load(scen.read_text())
    skill = yaml.safe_load(skill_path.read_text())
    skill["tests"] = [{"scenario": scen.stem, "expect_path": sc["expect_path"]}]
    skill_path.write_text(yaml.safe_dump(skill, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
    if promote:
        import promote as P
        rc = P.promote(skill_path)
        return skill_path, "✔ sim_verified" if rc == 0 else f"✘ promote rc={rc}"
    return skill_path, "✔ 已生成(未晋级)"


def generate_all(specs):
    ok, fail = [], []
    for spec in specs:
        try:
            p, st = generate(spec)
        except Exception as e:                                     # noqa: BLE001
            fail.append((spec["id"], f"✘ {e}"))
            continue
        (ok if st.startswith("✔ sim") else fail).append((spec["id"], st))
    return ok, fail
