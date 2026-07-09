#!/usr/bin/env python3
"""
OpsAxiom Skill 校验器（O-2）

用法：
    python tools/validate.py skills/            # 递归校验全部
    python tools/validate.py skills/host/disk-full/skill.yaml

两层校验：
  (a) 结构：schema/skill.schema.json（JSON Schema 2020-12）
  (b) 语义：规则 S1–S10（docs/03-skill-schema.md §4）
      - S5 表达式：exprlang.validate_when（fail-closed）
      - S6 语法树：syntax_check（本轮延后，INFO）
      - S9 模板变量来源：本轮 WARNING（schema 缺 params 声明，见 REVIEW-QUEUE R-1）

退出码：存在 ERROR → 1；仅 WARNING/INFO → 0。
"""
import argparse
import json
import pathlib
import re
import sys

import yaml
from jsonschema import Draft202012Validator

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA_PATH = ROOT / "schema" / "skill.schema.json"

sys.path.insert(0, str(HERE))
import exprlang            # noqa: E402
import syntax_check       # noqa: E402

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"
_BUILTIN_VARS = {"sid"}   # 引擎始终注入的会话级变量
_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.|]+)\s*\}\}")


class Report:
    def __init__(self, skill_path):
        self.path = skill_path
        self.items = []

    def add(self, level, rule, msg):
        self.items.append((level, rule, msg))

    @property
    def errors(self):
        return [i for i in self.items if i[0] == ERROR]

    def print(self):
        if not self.items:
            print(f"  ✔ {self.path}  (0 问题)")
            return
        icon = "✘" if self.errors else "•"
        print(f"  {icon} {self.path}")
        for level, rule, msg in self.items:
            tag = {"ERROR": "✘", "WARN": "⚠", "INFO": "ℹ"}[level]
            print(f"      {tag} [{rule}] {msg}")


def _platform_keys(run):
    return set(run.keys()) if isinstance(run, dict) else set()


def _iter_commands(node):
    """产出 (platform, command) 供 S6。"""
    for key in ("run", "dryrun"):
        obj = node.get(key)
        if isinstance(obj, dict):
            run = obj.get("run") if key == "dryrun" else obj
            if isinstance(run, dict):
                for p, c in run.items():
                    yield p, c


def _collect_template_vars(obj, acc):
    if isinstance(obj, str):
        for m in _TEMPLATE_RE.finditer(obj):
            acc.add(m.group(1).split("|")[0].split(".")[0])
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_template_vars(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_template_vars(v, acc)


def semantic_checks(skill, rep):
    meta = skill.get("metadata", {})
    tree = skill.get("tree", {})
    nodes = {n["id"]: n for n in tree.get("nodes", []) if isinstance(n, dict) and "id" in n}
    maturity = meta.get("maturity", "draft")

    # ---- 遍历节点 ----
    for nid, n in nodes.items():
        ntype = n.get("type")

        if ntype == "action":
            run_keys = _platform_keys(n.get("run"))
            rb = n.get("rollback", {})
            # S1 rollback 存在 + 平台键一致
            if not rb:
                rep.add(ERROR, "S1", f"action '{nid}' 缺 rollback")
            else:
                rbt = rb.get("type")
                # 校验回滚命令的平台键与 run 一致
                check_sets = []
                if isinstance(rb.get("run"), dict):
                    check_sets.append(("rollback.run", _platform_keys(rb["run"])))
                if rbt == "snapshot" and isinstance(rb.get("snapshot", {}).get("run"), dict):
                    check_sets.append(("rollback.snapshot.run", _platform_keys(rb["snapshot"]["run"])))
                if rbt == "transaction" and isinstance(rb.get("confirm", {}).get("run"), dict):
                    check_sets.append(("rollback.confirm.run", _platform_keys(rb["confirm"]["run"])))
                for label, ks in check_sets:
                    if ks != run_keys:
                        rep.add(ERROR, "S1",
                                f"action '{nid}' {label} 平台键 {sorted(ks)} 与 run {sorted(run_keys)} 不一致")
            # S2 risk>=medium → preflight + approval:required
            risk = n.get("risk")
            if risk in ("medium", "high", "critical"):
                pf = n.get("preflight")
                if not pf:
                    rep.add(ERROR, "S2", f"action '{nid}' risk={risk} 但缺 preflight")
                else:
                    if pf.get("approval") != "required":
                        rep.add(ERROR, "S2", f"action '{nid}' risk={risk} 的 preflight.approval 必须为 required")
                    for f in ("watch", "abort_if"):
                        if not pf.get(f):
                            rep.add(ERROR, "S2", f"action '{nid}' preflight 缺 {f}")
            # S3 verify 存在
            if not n.get("verify"):
                rep.add(ERROR, "S3", f"action '{nid}' 缺 verify")

        if ntype == "check":
            # S4 otherwise 存在
            if not n.get("otherwise"):
                rep.add(ERROR, "S4", f"check '{nid}' 缺 otherwise 兜底")
            # S5 每个 branch.when 可解析
            for i, br in enumerate(n.get("branch", [])):
                when = br.get("when", "")
                ok, err = exprlang.validate_when(when)
                if not ok:
                    rep.add(ERROR, "S5", f"check '{nid}' branch[{i}] when 非法：{err}  ← {when!r}")

    # ---- S7 goto 引用完整性 + 可达性 ----
    valid_targets = set(nodes) | {"escalate", "done", "rollback"}
    edges = {nid: set() for nid in nodes}

    def _ref(nid, target, where):
        if target is None:
            return
        if target not in valid_targets:
            rep.add(ERROR, "S7", f"'{nid}' {where} 指向不存在的节点 '{target}'")
        elif target in nodes:
            edges[nid].add(target)

    for nid, n in nodes.items():
        t = n.get("type")
        if t == "check":
            for br in n.get("branch", []):
                _ref(nid, br.get("goto"), "branch.goto")
            _ref(nid, n.get("otherwise"), "otherwise")
        elif t == "action":
            _ref(nid, n.get("goto"), "goto")
            onf = n.get("verify", {}).get("on_fail")
            if onf and onf != "rollback":       # rollback 是字面量，非跳转
                _ref(nid, onf, "verify.on_fail")
        elif t == "ask":
            for op in n.get("options", []):
                _ref(nid, op.get("goto"), "option.goto")

    entry = tree.get("entry")
    if entry not in nodes:
        rep.add(ERROR, "S7", f"entry '{entry}' 不是有效节点")
    else:
        seen, stack = set(), [entry]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(edges.get(cur, ()))
        for nid in nodes:
            if nid not in seen:
                rep.add(ERROR, "S7", f"节点 '{nid}' 不可达")

    # ---- S8 成熟度与测试一致性 ----
    if maturity in ("sim_verified", "field_verified", "certified"):
        tests = skill.get("tests", [])
        if not tests:
            rep.add(ERROR, "S8", f"maturity={maturity} 要求 tests 非空")
        elif not any(t.get("rollback_assert") for t in tests):
            rep.add(ERROR, "S8", f"maturity={maturity} 要求至少一个 tests 带 rollback_assert:true")

    # ---- S9 模板变量来源（本轮 WARNING，见 REVIEW-QUEUE R-1）----
    used = set()
    _collect_template_vars(skill.get("tree"), used)
    _collect_template_vars(skill.get("discovery"), used)
    sources = set(_BUILTIN_VARS)
    for f in meta.get("platforms", []):
        pass
    for fact in skill.get("requirements", {}).get("facts", []):
        sources.add(fact.split(".")[-1]); sources.add(fact.split(".")[0])
    for d in skill.get("discovery", []) or []:
        sources.add(d.get("id", ""))
    unsourced = sorted(v for v in used if v and v not in sources)
    if unsourced:
        rep.add(WARN, "S9",
                f"模板变量无显式来源（facts/discovery/builtin）：{unsourced}  "
                f"— 本轮不阻断，schema 待补 params 声明")

    # ---- S6 语法树（延后）----
    if syntax_check.is_deferred():
        rep.add(INFO, "S6", "命令语法树校验已延后至 O-5")


def _default_validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_skill(skill, label="<dict>", schema_validator=None):
    """校验一个已解析的 skill dict，返回 Report。供测试与 file 入口共用。"""
    rep = Report(label)
    sv = schema_validator or _default_validator()
    if not isinstance(skill, dict):
        rep.add(ERROR, "YAML", "顶层不是映射")
        return rep
    # (a) 结构校验
    for err in sorted(sv.iter_errors(skill), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        rep.add(ERROR, "SCHEMA", f"{loc}: {err.message}")
    # (b) 语义校验（结构错也继续跑，尽量多暴露问题）
    try:
        semantic_checks(skill, rep)
    except Exception as e:
        rep.add(ERROR, "SEMANTIC", f"语义校验内部异常：{e}")
    return rep


def validate_file(path, schema_validator):
    path = path.resolve()
    try:
        label = str(path.relative_to(ROOT))
    except ValueError:
        label = str(path)
    try:
        skill = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        rep = Report(label)
        rep.add(ERROR, "YAML", f"解析失败：{e}")
        return rep
    return validate_skill(skill, label, schema_validator)


def main():
    ap = argparse.ArgumentParser(description="OpsAxiom Skill 校验器")
    ap.add_argument("target", help="skill.yaml 文件或含 skill 的目录")
    args = ap.parse_args()

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    target = pathlib.Path(args.target)
    if target.is_file():
        files = [target]
    else:
        files = sorted(target.rglob("skill.yaml"))
    if not files:
        print("未找到 skill.yaml")
        return 2

    reports = [validate_file(f, validator) for f in files]
    n_err = sum(len(r.errors) for r in reports)
    n_skill = len(reports)
    bad = sum(1 for r in reports if r.errors)

    print(f"\n校验 {n_skill} 个 Skill：")
    for r in reports:
        r.print()
    print(f"\n结果：{n_skill - bad} 通过 / {bad} 失败 / {n_err} 个 ERROR\n")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
