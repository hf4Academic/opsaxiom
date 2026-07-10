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
ATT_SCHEMA_PATH = ROOT / "schema" / "attestation.schema.json"

sys.path.insert(0, str(HERE))
import exprlang            # noqa: E402
import syntax_check       # noqa: E402

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"
_BUILTIN_VARS = {"sid"}   # 引擎始终注入的会话级变量
_TEMPLATE_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")
_NODE_OUTPUT_ROOTS = {"rows", "output", "lines"}   # 节点/discovery 输出的裸引用根（§7.4）


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


def _is_noop_cmd(cmd):
    """判断命令是否为空转（echo/纯注释/空）。用于 S11。"""
    if not isinstance(cmd, str):
        return True
    c = cmd.strip()
    if not c or c.startswith("#"):
        return True
    # 逐条(以 && 或 ; 分隔)判断：全部是 echo 才算空转
    parts = re.split(r"&&|;", c)
    return all(p.strip().startswith("echo ") or not p.strip() for p in parts)


def _iter_commands(node):
    """产出 (platform, command) 供 S6：覆盖 run/dryrun/verify/preflight.watch/rollback。"""
    def emit(run):
        if isinstance(run, dict):
            for p, c in run.items():
                if isinstance(c, str):
                    yield p, c
    yield from emit(node.get("run"))
    if isinstance(node.get("dryrun"), dict):
        yield from emit(node["dryrun"].get("run"))
    if isinstance(node.get("verify"), dict):
        yield from emit(node["verify"].get("run"))
    if isinstance(node.get("preflight"), dict):
        for w in node["preflight"].get("watch", []) or []:
            if isinstance(w, dict):
                yield from emit(w.get("run"))
    rb = node.get("rollback")
    if isinstance(rb, dict):
        yield from emit(rb.get("run"))
        if isinstance(rb.get("snapshot"), dict):
            yield from emit(rb["snapshot"].get("run"))
        if isinstance(rb.get("confirm"), dict):
            yield from emit(rb["confirm"].get("run"))


def _collect_template_exprs(obj, acc):
    """收集所有 {{...}} 内部原始表达式字符串。"""
    if isinstance(obj, str):
        for m in _TEMPLATE_RE.finditer(obj):
            acc.add(m.group(1).strip())
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_template_exprs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_template_exprs(v, acc)


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
            # S3 verify 存在 + assert 可解析（v0.2 §7.2）
            v = n.get("verify")
            if not v:
                rep.add(ERROR, "S3", f"action '{nid}' 缺 verify")
            elif v.get("assert"):
                ok, err = exprlang.validate_when(v["assert"])
                if not ok:
                    rep.add(ERROR, "S5", f"action '{nid}' verify.assert 非法：{err}  ← {v['assert']!r}")
                else:
                    pok, perr = exprlang.check_projection(v["assert"])
                    if not pok:
                        rep.add(ERROR, "S12", f"action '{nid}' verify.assert 投影语义违规：{perr}  ← {v['assert']!r}")
            # S11 回滚不得空转（v0.2 §7.5）
            if rb:
                advisory = rb.get("advisory") is True
                if advisory and not n.get("human_only"):
                    rep.add(ERROR, "S11", f"action '{nid}' rollback.advisory 仅 human_only 节点可用")
                if not advisory:
                    cmds = []
                    if isinstance(rb.get("run"), dict):
                        cmds += list(rb["run"].values())
                    if isinstance(rb.get("snapshot", {}).get("run"), dict):
                        cmds += list(rb["snapshot"]["run"].values())
                    if isinstance(rb.get("confirm", {}).get("run"), dict):
                        cmds += list(rb["confirm"]["run"].values())
                    if cmds and all(_is_noop_cmd(c) for c in cmds):
                        rep.add(ERROR, "S11",
                                f"action '{nid}' 回滚全部为空转命令(echo/注释)——形式合规实质违宪(R1)；"
                                f"若确为人工指引，标 human_only + rollback.advisory:true")

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
                else:
                    pok, perr = exprlang.check_projection(when)
                    if not pok:
                        rep.add(ERROR, "S12", f"check '{nid}' branch[{i}] 投影语义违规：{perr}  ← {when!r}")

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

    # ---- F-4 facts 注册表成员检查（WARN）----
    reg = _facts_registry()
    if reg:
        for fact in skill.get("requirements", {}).get("facts", []):
            if fact not in reg:
                rep.add(WARN, "FACTS", f"fact '{fact}' 未在 tools/facts.yaml 注册（补注册或改用已注册 fact）")

    # ---- S8 成熟度与测试一致性（v0.2 精化，见 REVIEW-QUEUE R-6）----
    # rollback_assert 仅对含 action 的 Skill 强制；纯诊断 Skill 无写操作，路径覆盖即可。
    if maturity in ("sim_verified", "field_verified", "certified"):
        tests = skill.get("tests", [])
        has_action = any(n.get("type") == "action" for n in nodes.values())
        if not tests:
            rep.add(ERROR, "S8", f"maturity={maturity} 要求 tests 非空")
        elif has_action and not any(t.get("rollback_assert") for t in tests):
            rep.add(ERROR, "S8", f"maturity={maturity}：含 action 的 Skill 须有 rollback_assert:true 测试")

    # ---- S9 模板变量来源（v0.2 §7.1/§7.4：ERROR）----
    exprs = set()
    _collect_template_exprs(skill.get("tree"), exprs)
    _collect_template_exprs(skill.get("discovery"), exprs)
    discovery_ids = {d.get("id", "") for d in (skill.get("discovery") or [])}
    sources = set(_BUILTIN_VARS)                              # {sid}
    sources |= _NODE_OUTPUT_ROOTS                             # rows/output/lines 裸引用
    for fact in skill.get("requirements", {}).get("facts", []):
        sources.add(fact.split(".")[-1]); sources.add(fact.split(".")[0])
    for p in meta.get("params", []) or []:
        sources.add(p.get("name", ""))
    for n in nodes.values():
        if n.get("type") == "ask" and n.get("binds"):
            sources.add(n["binds"])
    for e in sorted(exprs):
        ok, root, second = exprlang.parse_template_ref(e)
        if not ok:
            rep.add(ERROR, "S9", f"模板 {{{{{e}}}}} 不是合法字段引用（v0.2 §7.4）")
            continue
        if root == "discovery":
            if second not in discovery_ids:
                rep.add(ERROR, "S9", f"模板 {{{{{e}}}}} 引用了不存在的 discovery id '{second}'")
        elif root not in sources:
            rep.add(ERROR, "S9",
                    f"模板变量 '{root}' 无来源（需在 facts/params/ask.binds/discovery 声明）：{{{{{e}}}}}")

    # ---- Q-2 字段来源校验（when/assert 引用的字段须由该节点 parser 产出，WARN 一轮）----
    try:
        import parsers as _parsers
        param_names = {p.get("name") for p in meta.get("params", []) or []}
        fact_roots = set()
        for fct in skill.get("requirements", {}).get("facts", []):
            fact_roots.add(fct.split(".")[-1]); fact_roots.add(fct.split(".")[0])
        base_ok = param_names | fact_roots | _BUILTIN_VARS | {"output"}
        for nid, n in nodes.items():
            if n.get("type") != "check":
                continue
            decl = _parsers.get_fields(n.get("parser", "")) if n.get("parser") else None
            if not decl:
                continue
            rows_fields = set(decl.get("rows", []))
            scalars = set(decl.get("scalars", []))
            lists = decl.get("lists", {}) or {}
            has_lines = decl.get("lines", False)
            for i, br in enumerate(n.get("branch", [])):
                for root, sub in exprlang.field_refs(br.get("when", "")):
                    if root.endswith("_before") or root in base_ok or root in scalars:
                        continue
                    if root == "rows":
                        if sub and rows_fields and sub not in rows_fields:
                            rep.add(WARN, "FIELD", f"check '{nid}' branch[{i}] rows.{sub} 不在解析器 {n['parser']} 声明的行字段 {sorted(rows_fields)}")
                        continue
                    if root == "lines":
                        continue
                    if root in lists:
                        continue
                    rep.add(WARN, "FIELD",
                            f"check '{nid}' branch[{i}] 字段 '{root}' 无来源（解析器 {n['parser']} 未声明，也非 fact/param）")
    except Exception:
        pass

    # ---- S6 命令语法树（O-5：网络平台强制，其他平台跳过）----
    checked_net = 0
    all_nodes = list(nodes.values())
    for d in skill.get("discovery", []) or []:
        all_nodes.append(d)
    for n in all_nodes:
        for platform, cmd in _iter_commands(n):
            for level, msg in syntax_check.check_command(platform, cmd):
                rep.add(level, "S6", f"[{n.get('id', 'discovery')}] {msg}")
            if platform in syntax_check.covered_platforms():
                checked_net += 1
    # ---- S9-parser：discovery/check 引用的 parser 是否存在（本轮 INFO）----
    try:
        import parsers
        for n in all_nodes:
            pname = n.get("parser")
            if pname and parsers.get_parser(pname) is None:
                rep.add(INFO, "PARSER", f"[{n.get('id', 'discovery')}] 解析器 '{pname}' 尚未实现（O-5 起逐步补齐）")
    except Exception:
        pass


def _default_validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


_FACTS_CACHE = None


def _facts_registry():
    global _FACTS_CACHE
    if _FACTS_CACHE is None:
        p = HERE / "facts.yaml"
        try:
            _FACTS_CACHE = set(yaml.safe_load(p.read_text(encoding="utf-8")).get("facts", {}))
        except Exception:
            _FACTS_CACHE = set()
    return _FACTS_CACHE


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


_ATT_VALIDATOR = None


def _att_validator():
    global _ATT_VALIDATOR
    if _ATT_VALIDATOR is None:
        try:
            _ATT_VALIDATOR = Draft202012Validator(json.loads(ATT_SCHEMA_PATH.read_text(encoding="utf-8")))
        except Exception:
            _ATT_VALIDATOR = False
    return _ATT_VALIDATOR


def _validate_attestations(skill_dir, rep):
    adir = skill_dir / "attestations"
    if not adir.is_dir():
        return
    av = _att_validator()
    if not av:
        return
    for af in sorted(adir.glob("*.yaml")):
        try:
            att = yaml.safe_load(af.read_text(encoding="utf-8"))
        except Exception as e:
            rep.add(ERROR, "ATTEST", f"{af.name} 解析失败：{e}")
            continue
        for err in av.iter_errors(att):
            loc = "/".join(str(p) for p in err.path) or "<root>"
            rep.add(ERROR, "ATTEST", f"{af.name} {loc}: {err.message}")


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
    rep = validate_skill(skill, label, schema_validator)
    _validate_attestations(path.parent, rep)
    return rep


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
