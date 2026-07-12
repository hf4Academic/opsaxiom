"""
Terminal REPL —— OpsAxiom 默认交互入口（W-1，docs/08 §4.2a）。

心智模型：像跟老师傅说话，不像查手册。裸敲 `opsaxiom` 就进来，敲字（说人话）就有反应。
- 非命令输入 = 症状 → diagnose top-3（自然语言是一等公民）
- 纯数字 = 选上次候选 → 原地进导航档（复用 runtime.Session，同进程）
- 少量内置词（可选，不学也能用）：help/list/info/run/doctor/hub/record/resume/quit
- Ctrl-C 中断当前 Skill 回提示符；空闲再 Ctrl-C/quit 退出。无 TTY 不进 REPL。

REPL 不复制任何业务逻辑：diagnose/run/attest 全走既有模块。
"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim"))
import yaml            # noqa: E402
import diagnose        # noqa: E402
import runtime         # noqa: E402
import incident as I   # noqa: E402  交互 v2：取证式诊断
import sweep           # noqa: E402
import llm             # noqa: E402  可选 LLM 适配层（无模型时全走降级）

_BADGE = {"draft": "⚪草稿", "sim_verified": "🔵已验证",
          "field_verified": "🟢实地", "certified": "🟡认证"}
_BUILTINS = {"help", "?", "list", "info", "run", "doctor", "hub", "record",
             "skill", "resume", "quit", "exit", "q", "sweep", "report", "model"}


def _find_skill(skill_id):
    for p in (ROOT / "skills").rglob("skill.yaml"):
        s = yaml.safe_load(p.read_text(encoding="utf-8"))
        if s.get("metadata", {}).get("id") == skill_id:
            return p, s
    return None, None


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


class Repl:
    def __init__(self):
        self.idx = diagnose.load_index()
        self.last_hits = []          # 上次 diagnose 的候选（供数字选择兜底）
        self.last_incident = None    # 上次陈述建立的 incident（供 sweep/report）
        self.running = True
        try:
            self.model_cfg = llm.load_config()   # None = 无模型，全走降级
        except Exception:
            self.model_cfg = None

    # ---------- 展示 ----------
    def _welcome(self):
        verified = sum(1 for s in self.idx if s["maturity"] != "draft")
        print(f"OpsAxiom v0.1 · {len(self.idx)} 个 Skill（{verified} 已验证）"
              f" · 输入你遇到的问题，或 help 看用法")

    def _show_hits(self, hits):
        if not hits:
            print("  没匹配到。换个说法试试，或 `list` 看全部域，或 `run <id>` 直接指定。")
            return
        print(f"  找到 {len(hits)} 个匹配：")
        for i, (_, sk) in enumerate(hits, 1):
            print(f"  {i}) [{_BADGE.get(sk['maturity'], sk['maturity'])}] {sk['name']}"
                  f"       {sk['id']}")
            if sk.get("symptom"):
                print(f"       {sk['symptom']}")
        print("  → 输入序号进入排查，或继续描述别的问题。")

    # ---------- 内置词 ----------
    def _help(self):
        print("""用法（大多数时候你只需要直接描述问题）：
  直接说问题        如：磁盘满了但df有空间 / gpu掉卡 xid 79 / kafka积压
                    交互态会自动一键取证并出诊断卷宗（证实/排除/证据不足）
  加参数            结尾带 k=v，如：磁盘满了 mount=/data（无模型时显式给实体）
  sweep             对刚才的陈述一键取证：本机只读自动跑/远端出粘贴块 → 诊断卷宗
  report            把当前卷宗导出为故障报告 markdown（可贴工单/转人工）
  <数字>            兜底：进入某个假设的逐步排查（老导航档）
  list [域]         列出全部或某域的 Skill（域：host k8s network middleware aicomp obs sec proc）
  info <id>         看某个 Skill 的概况
  run <id>          直接进入某个 Skill 的排查
  resume            续跑上次中断的排查
  model             配置/测试 LLM 后端（show/use/test/pull；内置千问0.5B/Ollama/远程API/pi）
  doctor            环境自检
  hub / record / skill …   Skills Hub 与经验捕获（见手册 docs/10）
  quit / Ctrl-C     退出""")

    def _list(self, dom=None):
        rows = [s for s in self.idx if not dom or s["l1"] == dom]
        rows.sort(key=lambda s: s["id"])
        cur = None
        for s in rows:
            if s["l1"] != cur:
                cur = s["l1"]
                print(f"\n  {cur}")
            print(f"    [{_BADGE.get(s['maturity'], s['maturity'])}] {s['id']}  —— {s['name']}")
        print()

    def _info(self, sid):
        p, s = _find_skill(sid)
        if not p:
            print(f"  没有这个 Skill：{sid}")
            return
        m = s["metadata"]
        nodes = s.get("tree", {}).get("nodes", [])
        adir = p.parent / "attestations"
        n_att = len(list(adir.glob("*.yaml"))) if adir.is_dir() else 0
        print(f"  {m['name']}  [{_BADGE.get(m['maturity'], m['maturity'])}]")
        print(f"    id: {m['id']} · 分类: {m['taxonomy']} · v{m['version']}")
        print(f"    决策树: {len(nodes)} 个节点 · 实地验证记录: {n_att}")
        cauts = [c for n in nodes for c in (n.get("cautions") or [])][:3]
        for c in cauts:
            print(f"    ⚠ {c[:88]}")
        print(f"  → run {m['id']} 开始排查")

    def _run(self, skill_id, resume=False, session_id=None):
        p, s = _find_skill(skill_id)
        if not p:
            print(f"  没有这个 Skill：{skill_id}")
            return
        io = runtime.IO(answers=None, echo=True)
        # F-14：resume 必须用状态文件的真实 sid（可能来自子命令/自定义 --sid），
        # 不能由 skill_id 重新派生——否则刚列出的会话选中后找不到状态
        session_id = session_id or skill_id.replace(".", "_") + "-repl"
        sess = runtime.Session(p, params={}, mode="guided", io=io, sid=session_id)
        start = None
        if resume:
            start = sess.load_state()
            if not start:
                print("  没有可续跑的进度。")
                return
        print(f"\n进入：{s['metadata']['name']}（导航档：你敲命令，Agent 只出方案与判读）")
        try:
            res = sess.run(start=start)
        except KeyboardInterrupt:
            print("\n  ⏸ 已中断本次排查（进度已存）。输入 resume 可续跑，或继续描述别的问题。")
            return
        if res["outcome"] == "quit":
            print("  已退出本次排查（进度已存，输入 resume 续跑）。")

    def _resume_pick(self):
        sd = _home() / "sessions"
        states = sorted(sd.glob("*.state.json")) if sd.is_dir() else []
        if not states:
            print("  没有可续跑的排查。")
            return
        import json
        print("  可续跑的排查：")
        metas = []
        for i, st in enumerate(states, 1):
            d = json.loads(st.read_text(encoding="utf-8"))
            d["_sid"] = st.name[: -len(".state.json")]   # 状态文件名 = 真实 sid
            metas.append(d)
            print(f"  {i}) {d.get('skill_id')}  停在节点 {d.get('node')}")
        sel = input("  选择序号续跑（回车取消）: ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(metas):
            m = metas[int(sel) - 1]
            self._run(m["skill_id"], resume=True, session_id=m["_sid"])

    # ---------- 交互 v2：陈述 → 取证 → 卷宗 ----------
    @staticmethod
    def _parse_symptom(line):
        """从陈述里剥出结尾的 k=v 参数（如 `磁盘满 mount=/data`）。
        Z-5 的 LLM intake 会把这一步自动化（从自然语言抽实体）；无模型时靠这个显式兜底。"""
        toks = line.split()
        params, rest = {}, []
        for t in toks:
            if "=" in t and t.split("=")[0].isidentifier():
                k, v = t.split("=", 1)
                params[k] = v
            else:
                rest.append(t)
        return " ".join(rest), params

    def _show_hypotheses(self, inc):
        print(f"  假设 {len(inc.hyps)} 个（按相关度）：")
        for i, h in enumerate(inc.hyps, 1):
            print(f"  {i}) [{h.badge}] {h.name}       {h.meta['id']}")

    def _llm_prefill(self, symptom, params):
        """有模型则从自然语言预填 params（显式 k=v 优先）；无模型原样返回。R11/T-3 由 llm 层保证。"""
        if self.model_cfg is None:
            return params
        r = llm.intake(symptom, config=self.model_cfg)
        prefilled = {k: v for k, v in r.get("params", {}).items() if k not in params}
        if prefilled:
            shown = ", ".join(f"{k}={v}" for k, v in prefilled.items())
            print(f"  （从你的描述预填：{shown}——回车确认，或输 k=v 覆盖）")
        return {**prefilled, **params}

    def _intake(self, line):
        """陈述入口：建 incident、列假设。交互态自动接一键取证；非 TTY 只列假设（不阻塞）。"""
        symptom, params = self._parse_symptom(line)
        params = self._llm_prefill(symptom, params)
        self.last_hits = diagnose.match(symptom, idx=self.idx, top=3)
        if not self.last_hits:
            self._show_hits(self.last_hits)
            return
        skills = []
        for _, e in self.last_hits:
            _, s = I.load_skill_by_id(e["id"])
            if s:
                skills.append(s)
        inc = I.Incident(symptom, params=params, target=I.LOCAL)
        inc.add_hypotheses(skills)
        self.last_incident = inc
        self._show_hypotheses(inc)
        if sys.stdin.isatty():
            self._sweep_incident()
        else:
            print("  → 输入 sweep 一键取证出诊断卷宗，或输序号进入某假设逐步排查。")

    def _read_until_end(self):
        lines = []
        for line in sys.stdin:
            if line.strip() == "END":
                break
            lines.append(line.rstrip("\n"))
        return "\n".join(lines)

    def _sweep_incident(self):
        """一键取证：本机只读自动执行（需一次性授权）+ 远端/手动命令单粘贴块 → 干跑 → 卷宗。"""
        inc = self.last_incident
        if not inc:
            print("  先描述一个问题，我才好取证。")
            return
        plan = inc.plan()
        auto = [p for w in plan["waves"] for p in w["probes"] if p["auto"]]
        if inc.target == I.LOCAL and auto:
            if not sweep.is_trusted(I.LOCAL):
                print(f"  本机可自动执行 {len(auto)} 条只读取证命令（均出自已验证 Skill，绝不含写操作）。")
                try:
                    ans = input("  授权本机自动取证？一次性，记 trust.yaml [y/N]: ")
                except (EOFError, KeyboardInterrupt):
                    ans = ""
                if ans.strip().lower() in ("y", "yes", "是"):
                    sweep.grant_trust(I.LOCAL)
            if sweep.is_trusted(I.LOCAL):
                print("  ▶ 取证中（本机只读自动执行）…")
                inc.auto_sweep()
        nonce = sweep.make_nonce()
        block, probes = inc.paste_block(nonce, only_manual=True)
        if probes:
            print(block)
            print("  贴回全部输出，单独一行 END 结束：")
            try:
                pasted = self._read_until_end()
            except (EOFError, KeyboardInterrupt):
                pasted = ""
            if pasted.strip():
                inc.ingest(pasted, nonce)
        inc.dry_run()
        print(inc.render_dossier())
        self._offer_treatment(inc)

    def _offer_treatment(self, inc):
        for h in inc.hyps:
            if h.status == I.CONFIRMED and h.pending:
                print(f"  → 处置：run {h.meta['id']}"
                      f"（进入导航档执行变更，变更简报/审批门/verify 不变）")
                return
        if all(h.status != I.CONFIRMED for h in inc.hyps):
            print("  未证实任何假设。输入 report 导出移交卷宗，转人工/强模型接手。")
            if self.model_cfg is not None:           # escalate 助理：只荐库内 id（R8/R10）
                sid = llm.suggest_skill(inc.handover(), self.idx, config=self.model_cfg)
                if sid:
                    print(f"  → 模型建议再看：run {sid}（库内 Skill，徽章以库为准）")

    def _report(self):
        if not self.last_incident:
            print("  还没有可导出的排查。先描述问题并 sweep。")
            return
        print(self.last_incident.export_report())

    def _delegate(self, parts):
        """hub/record/skill/doctor 交给既有 CLI 模块处理（复用，不复制）。"""
        import argparse
        ap = argparse.ArgumentParser(prog="opsaxiom", add_help=False)
        sub = ap.add_subparsers(dest="cmd")
        for mod, fn in (("doctor", "add_doctor"), ("capture_cli", "add_capture"),
                        ("hub_cli", "add_hub"), ("model_cli", "add_model")):
            try:
                m = __import__(mod)
                getattr(m, fn)(sub)
            except Exception:
                pass
        try:
            args = ap.parse_args(parts)
        except SystemExit:
            return
        if hasattr(args, "fn"):
            try:
                args.fn(args)
            except Exception as e:
                print(f"  出错：{e}")

    # ---------- 主循环 ----------
    def _handle(self, line):
        line = line.strip()
        if not line:
            return
        parts = line.split()
        head = parts[0].lower()
        if head in ("quit", "exit", "q"):
            self.running = False
            return
        if head in ("help", "?"):
            self._help(); return
        if head == "list":
            self._list(parts[1] if len(parts) > 1 else None); return
        if head == "info" and len(parts) > 1:
            self._info(parts[1]); return
        if head == "run" and len(parts) > 1:
            self._run(parts[1]); return
        if head == "resume":
            self._resume_pick(); return
        if head == "sweep":
            self._sweep_incident(); return
        if head == "report":
            self._report(); return
        if head in ("doctor", "hub", "record", "skill", "model"):
            self._delegate(parts)
            if head == "model":                     # 配置可能变了，热重载
                try:
                    self.model_cfg = llm.load_config()
                except Exception:
                    self.model_cfg = None
            return
        if line.isdigit():
            i = int(line)
            if 1 <= i <= len(self.last_hits):
                self._run(self.last_hits[i - 1][1]["id"])
            else:
                print("  没有这个序号。先描述问题看到候选，再输序号。")
            return
        # 默认：当症状 → 陈述入口（交互 v2：建 incident、列假设、交互态自动取证）
        self._intake(line)

    def loop(self):
        try:
            import readline  # noqa: F401  上下键历史
            hist = _home() / "history"
            _home().mkdir(parents=True, exist_ok=True)
            try:
                readline.read_history_file(str(hist))
            except Exception:
                pass
        except Exception:
            hist = None
        self._welcome()
        # M-2 首次向导：model.yaml 不存在且在真终端 → 问一次（任何选择都落盘不再问）
        if not llm.config_path().exists() and sys.stdin.isatty():
            try:
                import model_cli
                model_cli.first_run_wizard()
                self.model_cfg = llm.load_config()
            except Exception:
                pass
        idle_interrupt = False
        while self.running:
            try:
                line = input("axiom> ")
                idle_interrupt = False
                self._handle(line)
            except KeyboardInterrupt:
                if idle_interrupt:
                    print("\n再见。")
                    break
                print("\n（再按一次 Ctrl-C 退出，或 quit）")
                idle_interrupt = True
            except EOFError:
                print("\n再见。")
                break
        if hist:
            try:
                import readline
                readline.write_history_file(str(hist))
            except Exception:
                pass


def start():
    if not sys.stdin.isatty():
        print("OpsAxiom 交互态需要终端。脚本/自动化请用子命令："
              "opsaxiom diagnose \"<症状>\" 或 opsaxiom run <id>。", file=sys.stderr)
        return 2
    Repl().loop()
    return 0
