"""
经验捕获（V-2，docs/08 §1）——把日常排查变成 Skill 草稿。

三条通道共用同一条"审计 jsonl → skill.yaml 草稿"管线：
  · from-session：导航档跑完的会话审计（sessions/<sid>.jsonl）
  · record：没走 Skill 时的投喂式记录（record 写同格式的 jsonl）
  · new：向导问答，直接产结构化草稿
产物一律落 skills-drafts/，是 draft，过既有 validate→sim→promote 流水线才升级。
降低的是写作成本，不是认证门槛。
"""
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim"))
import yaml            # noqa: E402


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


def _sessions_dir():
    d = _home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drafts_dir():
    d = ROOT / "skills-drafts"
    d.mkdir(exist_ok=True)
    return d


def _slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "captured"


def _read_audit(sid):
    f = _sessions_dir() / f"{sid}.jsonl"
    if not f.exists():
        raise FileNotFoundError(f"找不到会话审计：{f}")
    recs = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            recs.append(json.loads(line))
    return recs


# ---------- 通道一/二共用：审计 → 草稿 ----------
def draft_from_audit(recs, skill_id, name, taxonomy):
    """把审计记录回放成 skill.yaml 草稿 + 配套 sim node_ctx 草稿。

    只知道人实际走过的路径（不知道未走的分支），故生成**线性骨架**：
    walked check → 单分支到下一节点 + otherwise:escalate + cautions:[TODO]；
    终点 done 用人的结论/反馈占位。作者补全分支与 caution 后走正常流水线。
    """
    checks = [r for r in recs if r.get("type") == "check"]
    node_ctx = {}
    nodes = []
    entry = None
    prev_id = None
    for i, r in enumerate(checks):
        nid = r["node"]
        entry = entry or nid
        nxt = f"exit_done" if i == len(checks) - 1 else checks[i + 1]["node"]
        nodes.append({
            "id": nid, "type": "check",
            "title": f"TODO 描述这一步在查什么（{nid}）",
            "run": {"linux": r.get("cmd", "echo TODO")},
            # 用合法的占位判据让草稿结构可跑；真实判据由作者按 gap 提示替换
            "branch": [{"when": "count(rows) > 0", "goto": nxt}],
            "otherwise": "escalate",
            "cautions": ["TODO 写一条真实的'坑'（docs/07 D4：会让人踩坑的具体事实，不是废话）"],
        })
        # 输出摘要 → sim node_ctx 草稿（作者据此填结构化上下文）
        if r.get("output"):
            node_ctx[nid] = {"_raw_output_sample": r["output"]}
        prev_id = nid
    # 终点
    fb = next((r.get("answer") for r in recs if r.get("type") == "feedback"), "")
    nodes.append({"id": "exit_done", "type": "done",
                  "summary": f"TODO 写结论与后续建议。人在本次会话的反馈：{fb or '（无）'}"})
    nodes.append({"id": "escalate", "type": "escalate",
                  "summary": "TODO 打包升级：列出需要人工判断时应附带的证据。"})

    skill = {
        "apiVersion": "skill/v0.1", "kind": "Diagnostic",
        "metadata": {
            "id": skill_id, "name": name,
            "taxonomy": taxonomy, "version": "0.1.0", "maturity": "draft",
            "platforms": [{"os": "linux"}],
            "authors": ["captured"], "license": "Apache-2.0",
            "provenance": {"generated_by": "human-session"},
            "expires_review": "2027-07-01",
        },
        "requirements": {"capability_level": "read", "connectors": ["ssh"]},
        "tree": {"entry": entry or "exit_done", "nodes": nodes},
        "tests": [{"scenario": "tests/captured.yaml",
                   "expect_path": [c["node"] for c in checks] + ["exit_done"]}],
        "feedback": {"ask": "这个问题定位了吗？"},
    }
    return skill, node_ctx


def write_draft(skill, node_ctx, slug):
    d = _drafts_dir() / slug
    d.mkdir(parents=True, exist_ok=True)
    sf = d / "skill.yaml"
    sf.write_text(yaml.safe_dump(skill, allow_unicode=True, sort_keys=False), encoding="utf-8")
    scen = {"skill": f"skills-drafts/{slug}/skill.yaml",
            "scenario": "捕获草稿（待作者补全 node_ctx）",
            "expect_path": skill["tests"][0]["expect_path"],
            "node_ctx": node_ctx}
    (d / "captured-scenario.yaml").write_text(
        yaml.safe_dump(scen, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return sf


def from_session(sid, skill_id, name, taxonomy):
    recs = _read_audit(sid)
    skill, node_ctx = draft_from_audit(recs, skill_id, name, taxonomy)
    slug = _slugify(skill_id.split(".")[-1])
    return write_draft(skill, node_ctx, slug)


# ---------- 通道二：record ----------
def _cur_rec_file():
    return _home() / "recording.current"


def record_start(name):
    sid = f"rec-{_slugify(name)}"
    (_sessions_dir() / f"{sid}.jsonl").write_text("", encoding="utf-8")
    _cur_rec_file().write_text(sid, encoding="utf-8")
    return sid


def _append_rec(rec):
    p = _cur_rec_file()
    if not p.exists():
        raise RuntimeError("没有进行中的记录会话，先 record start <name>")
    sid = p.read_text().strip()
    with (_sessions_dir() / f"{sid}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return sid


def record_exec(cmd):
    """代跑只读命令并留痕（复用 sim 的只读白名单，拒绝写操作——R11/安全边界）。"""
    import run_sim
    if not run_sim._is_readonly(cmd):
        raise PermissionError(f"record exec 只允许只读命令（白名单外）：{cmd}")
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=30).stdout
    summ = " ".join(out.split())[:200]
    step = f"step_{_step_no()}"
    _append_rec({"node": step, "type": "check", "cmd": cmd, "output": summ})
    return step, summ


def record_note(cmd, output):
    """人手工投喂一步（命令 + 粘贴的输出）。"""
    step = f"step_{_step_no()}"
    _append_rec({"node": step, "type": "check", "cmd": cmd, "output": " ".join((output or '').split())[:200]})
    return step


def _step_no():
    sid = _cur_rec_file().read_text().strip()
    recs = _read_audit(sid)
    return len([r for r in recs if r.get("type") == "check"]) + 1


def record_stop():
    p = _cur_rec_file()
    sid = p.read_text().strip() if p.exists() else None
    if p.exists():
        p.unlink()
    return sid


# ---------- 通道三：向导 ----------
def wizard(inp=input):
    name = inp("这个问题叫什么（一句话症状）？ ").strip()
    taxonomy = inp("归到哪个分类（如 host/process/xxx）？ ").strip()
    skill_id = taxonomy.replace("/", ".")
    n = int(inp("分几种情况判断？(1-5) ").strip() or "2")
    cmd = inp("第一步查什么命令？ ").strip()
    nodes = [{"id": "check1", "type": "check", "title": name,
              "run": {"linux": cmd}, "branch": [], "otherwise": "escalate",
              "cautions": [inp("这一步有什么坑要提醒？ ").strip() or "TODO"]}]
    for i in range(n):
        cond = inp(f"情况{i+1}的判据表达式（如 count(rows)>0）？ ").strip()
        concl = inp(f"情况{i+1}的结论/处置方向？ ").strip()
        eid = f"exit{i+1}"
        nodes[0]["branch"].append({"when": cond or "TODO", "goto": eid})
        nodes.append({"id": eid, "type": "done", "summary": concl or "TODO"})
    nodes.append({"id": "escalate", "type": "escalate", "summary": "TODO 打包升级证据"})
    skill = {
        "apiVersion": "skill/v0.1", "kind": "Diagnostic",
        "metadata": {"id": skill_id, "name": name, "taxonomy": taxonomy,
                     "version": "0.1.0", "maturity": "draft", "platforms": [{"os": "linux"}],
                     "authors": ["captured"], "license": "Apache-2.0",
                     "provenance": {"generated_by": "human-wizard"},
                     "expires_review": "2027-07-01"},
        "requirements": {"capability_level": "read", "connectors": ["ssh"]},
        "tree": {"entry": "check1", "nodes": nodes},
        "tests": [{"scenario": "tests/w.yaml", "expect_path": ["check1", "exit1"]}],
        "feedback": {"ask": f"{name} 定位了吗？"},
    }
    return write_draft(skill, {}, _slugify(skill_id.split(".")[-1]))


# ---------- lint：validate + 缺口清单 ----------
def lint(path):
    import json as _json
    import validate
    from jsonschema import Draft202012Validator
    p = pathlib.Path(path)
    sv = Draft202012Validator(_json.loads(validate.SCHEMA_PATH.read_text(encoding="utf-8")))
    rep = validate.validate_file(p, sv)
    gaps = []
    try:
        s = yaml.safe_load(p.read_text(encoding="utf-8"))
        for n in s.get("tree", {}).get("nodes", []):
            if n.get("type") == "check":
                if not n.get("cautions") or any("TODO" in str(c) for c in n.get("cautions", [])):
                    gaps.append(f"节点 {n['id']}：cautions 待补真实的'坑'（docs/07 D4）")
                if len(n.get("branch", []) or []) <= 1:
                    gaps.append(f"节点 {n['id']}：只有一条分支（线性骨架），补全其余情况的判据与去向")
            if n.get("type") == "action" and not n.get("rollback"):
                gaps.append(f"节点 {n['id']}：action 缺 rollback（R1/S1）")
            if "TODO" in str(n.get("title", "")) or "TODO" in str(n.get("summary", "")):
                gaps.append(f"节点 {n['id']}：title/summary 还是 TODO")
    except Exception as e:
        gaps.append(f"解析失败：{e}")
    return rep, gaps
