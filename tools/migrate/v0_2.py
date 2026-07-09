#!/usr/bin/env python3
"""
v0.1 → v0.2 迁移脚本（P-1）。用于 29 个无注释的生成 Skill（round-trip）；
两个金标准(disk-full/bgp)含教学注释，改由人工 Edit 迁移，不走本脚本。

迁移动作：
  1. 模板别名拍平：{{rowsN_field}} -> {{rows[N].field}}
  2. 工具名/路径：opsagent-* -> opsaxiom-*，/var/lib/opsagent/ -> /var/lib/opsaxiom/
  3. verify.expect -> verify.assert（原值原样搬；散文 assert 会被校验器揪出，人工补）
  4. ask 节点补 binds: null（有产出的由人工改具体变量名）
  5. metadata.params：为所有无来源模板根补 {name, source: alert}（source 由人工精修）
用法：python tools/migrate/v0_2.py <skill.yaml>...
"""
import pathlib
import re
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import exprlang  # noqa: E402

_ALIAS = re.compile(r"\{\{\s*rows(\d+)_(\w+)\s*\}\}")
_NODE_ROOTS = {"rows", "output", "lines"}
_BUILTIN = {"sid"}


def _text_fixes(raw):
    raw = _ALIAS.sub(r"{{rows[\1].\2}}", raw)
    raw = raw.replace("opsagent-quarantine", "opsaxiom-quarantine")
    raw = raw.replace("opsagent-deploy", "opsaxiom-deploy")
    raw = raw.replace("/var/lib/opsagent/", "/var/lib/opsaxiom/")
    return raw


def _collect_exprs(obj, acc):
    if isinstance(obj, str):
        for m in re.finditer(r"\{\{\s*(.+?)\s*\}\}", obj):
            acc.add(m.group(1).strip())
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_exprs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_exprs(v, acc)


def migrate(path):
    raw = _text_fixes(pathlib.Path(path).read_text(encoding="utf-8"))
    skill = yaml.safe_load(raw)
    nodes = skill.get("tree", {}).get("nodes", [])

    # verify.expect -> assert; ask binds
    for n in nodes:
        v = n.get("verify")
        if isinstance(v, dict) and "expect" in v and "assert" not in v:
            v["assert"] = v.pop("expect")
        if n.get("type") == "ask" and "binds" not in n:
            # 有产出的 ask 由人工改名；默认 null
            n["binds"] = None

    # 计算无来源模板根 -> params
    exprs = set()
    _collect_exprs(skill.get("tree"), exprs)
    _collect_exprs(skill.get("discovery"), exprs)
    discovery_ids = {d.get("id") for d in (skill.get("discovery") or [])}
    sources = set(_BUILTIN) | _NODE_ROOTS
    for f in skill.get("requirements", {}).get("facts", []):
        sources.add(f.split(".")[-1]); sources.add(f.split(".")[0])
    for n in nodes:
        if n.get("type") == "ask" and n.get("binds"):
            sources.add(n["binds"])
    need = []
    for e in sorted(exprs):
        ok, root, second = exprlang.parse_template_ref(e)
        if not ok:
            continue
        if root == "discovery" or root in sources:
            continue
        if root not in need:
            need.append(root)
    if need:
        existing = {p["name"] for p in skill["metadata"].get("params", [])}
        params = skill["metadata"].get("params", [])
        for name in need:
            if name not in existing:
                params.append({"name": name, "source": "alert"})
        # 放到 platforms 之后：重建 metadata 顺序
        skill["metadata"]["params"] = params

    out = yaml.dump(skill, allow_unicode=True, sort_keys=False, default_flow_style=None, width=100)
    pathlib.Path(path).write_text(out, encoding="utf-8")
    return need


if __name__ == "__main__":
    for p in sys.argv[1:]:
        need = migrate(p)
        print(f"migrated {p}  params+={need}")
