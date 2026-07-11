"""
运行时引擎——导航档（Navigator）会话（T-1，落实 docs/01 §2 第一档 + R3/R5/R6）。

导航档语义：Agent 只出方案、变更简报、判读，**人执行一切命令**（写操作 Agent 绝不代执行）。
每一步"执行→采集输出→机器判读→符合预期才放行下一步"（R5）。风险操作前渲染变更简报（R6）。

输入抽象 IO：交互式读 stdin，或脚本驱动（答案文件，供测试/演示非交互运行）。
审计：每步落 ~/.opsaxiom/sessions/<sid>.jsonl（R11 脱敏；这里只记节点/决策/输入摘要）。

模板渲染（§7.4/§7.6c，落实 R-7）：`{{expr}}` 用受限表达式求值器对当前上下文求值，
支持 {{mount}}(param) / {{rows[0].comm}} / {{output.pcent}}(节点标量) / {{sid}}。
"""
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim"))
import yaml            # noqa: E402
import exprlang        # noqa: E402
import parsers         # noqa: E402
import run_sim         # noqa: E402  复用 _is_readonly / _default_parse

_TEMPLATE = re.compile(r"\{\{\s*(.+?)\s*\}\}")
MISSING = "⟨?⟩"          # 字段缺失占位（U-1：别再渲染成空串留下语义黑洞）


def render(text, ctx):
    """把 {{expr}} 用受限求值器渲染。

    - 求值成功但为 None（字段在 ctx 里缺失）→ 显示 MISSING 占位，
      而非空串（四轮评审：空串会让"共 X 个"渲染成"共 　个"这类语义黑洞）。
    - 求值抛异常（语法/求值器问题）→ 保留原样 {{...}}，不崩。
    """
    if not isinstance(text, str):
        return text

    def repl(m):
        try:
            v = exprlang.evaluate(m.group(1), ctx)
            return MISSING if v is None else str(v)
        except Exception:
            return m.group(0)
    return _TEMPLATE.sub(repl, text)


class IO:
    """交互 or 脚本。脚本模式：answers[node_id] 提供该节点的人类输入。"""
    def __init__(self, answers=None, echo=True):
        self.answers = answers          # dict|None
        self.echo = echo
        self.transcript = []

    def _p(self, s=""):
        if self.echo:
            print(s)

    def paste(self, node, prompt):
        """check：粘贴命令输出（脚本模式取 answers[node]，交互模式读到 END）。"""
        self._p(prompt)
        if self.answers is not None:
            return self.answers.get(node, "")
        lines = []
        for line in sys.stdin:
            if line.strip() == "END":
                break
            lines.append(line.rstrip("\n"))
        return "\n".join(lines)

    def choose(self, node, prompt, options):
        self._p(prompt)
        for i, o in enumerate(options, 1):
            self._p(f"  {i}) {o['label']}")
        if self.answers is not None:
            a = str(self.answers.get(node, "1")).strip()
            idx = int(a) if a.isdigit() else next((i for i, o in enumerate(options, 1) if o["label"] == a), 1)
        else:
            idx = int(input("选择 [1-%d]: " % len(options)) or "1")
        idx = max(1, min(idx, len(options)))
        return idx - 1

    def confirm(self, node, prompt):
        self._p(prompt)
        if self.answers is not None:
            return str(self.answers.get(node, "n")).strip().lower() in ("y", "yes", "是")
        return input("[y/N]: ").strip().lower() in ("y", "yes")

    def attest_intake(self, node, prompt):
        """V-3 一键认证：返回预填字段的补充 dict，或 None 表示跳过。

        脚本模式：answers[node+':attest'] 为 dict（补 os_family/scale/attestor）或缺省=跳过。
        交互模式：先 y/N，y 则只问 os-family 与规模两个分桶。
        """
        if self.answers is not None:
            info = self.answers.get(node + ":attest")
            return info if isinstance(info, dict) else None
        self._p(f"\n{prompt} [y/N]")
        if input("> ").strip().lower() not in ("y", "yes", "是"):
            return None
        return {"os_family": input("  os 家族 [linux]: ").strip() or "linux",
                "scale": input("  规模(主机数) [1]: ").strip() or "1",
                "attestor": input("  你的标识 (gh:user) [anonymous]: ").strip() or "anonymous"}

    def action_decision(self, node, prompt):
        """变更节点决策（U-1：不再是 y/n 二选一）。返回 proceed|skip|escalate|quit。

        脚本兼容：答案 y/yes/是→proceed，n/no→escalate（沿用旧 demo），
        另接受显式 proceed/skip/escalate/quit 或序号 1-4。
        """
        self._p(prompt)
        opts = ["确认，我将亲自执行此变更", "跳过此步（不执行，继续后续排查）",
                "升级人工处理", "退出会话"]
        keys = ["proceed", "skip", "escalate", "quit"]
        if self.answers is not None:
            a = str(self.answers.get(node, "n")).strip().lower()
            if a in ("y", "yes", "是"):
                return "proceed"
            if a in ("n", "no", "否"):
                return "escalate"
            if a in keys:
                return a
            if a.isdigit() and 1 <= int(a) <= 4:
                return keys[int(a) - 1]
            return "escalate"
        for i, o in enumerate(opts, 1):
            self._p(f"  {i}) {o}")
        raw = input("选择 [1-4，默认 3 升级]: ").strip() or "3"
        idx = int(raw) if raw.isdigit() and 1 <= int(raw) <= 4 else 3
        return keys[idx - 1]


class Session:
    def __init__(self, skill_path, params=None, mode="guided", io=None, sid="sess"):
        self.skill = yaml.safe_load(pathlib.Path(skill_path).read_text(encoding="utf-8"))
        self.nodes = {n["id"]: n for n in self.skill["tree"]["nodes"]}
        self.entry = self.skill["tree"]["entry"]
        self.mode = mode              # guided | real
        self.io = io or IO()
        self.sid = sid
        self.ctx = dict(params or {})
        self.ctx["sid"] = sid
        self.path = []
        self.audit = []
        self.outcome = None

    # ---- 审计 ----
    @staticmethod
    def _summ(text, limit=200):
        """粘贴输出摘要：压平空白、截断（审计留证据但不灌爆）。"""
        s = " ".join((text or "").split())
        return s if len(s) <= limit else s[:limit] + "…"

    def _log(self, node, ntype, **kw):
        self.audit.append({"node": node, "type": ntype, **kw})

    def _sess_dir(self):
        d = pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom")) / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _write_audit(self):
        f = self._sess_dir() / f"{self.sid}.jsonl"
        with f.open("w", encoding="utf-8") as fh:
            for rec in self.audit:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return f

    def _write_state(self, node):
        """断点续跑状态（U-1）：每步落 ctx + 下一节点 + 已走路径。

        只对真实节点存档；控制/终止 token（__quit__/escalate/done/…）不覆盖，
        这样 quit 后 state 仍指向那个待执行的真实节点，resume 从它重跑。
        """
        if node not in self.nodes:
            return
        f = self._sess_dir() / f"{self.sid}.state.json"
        try:
            f.write_text(json.dumps(
                {"skill_id": self.skill["metadata"]["id"], "node": node,
                 "ctx": self.ctx, "path": self.path, "mode": self.mode,
                 "audit": self.audit}, ensure_ascii=False), encoding="utf-8")
        except TypeError:
            pass          # ctx 含不可序列化对象时跳过（不影响主流程）

    def load_state(self):
        """从 state.json 恢复；返回续跑起点节点，无则 None。"""
        f = self._sess_dir() / f"{self.sid}.state.json"
        if not f.exists():
            return None
        st = json.loads(f.read_text(encoding="utf-8"))
        self.ctx = st.get("ctx", self.ctx)
        self.path = st.get("path", [])
        self.mode = st.get("mode", self.mode)
        self.audit = st.get("audit", [])
        return st.get("node")

    # ---- 渲染 ----
    def r(self, text):
        return render(text, self.ctx)

    def _cmd_for(self, run):
        """取 linux/kubectl/... 任一平台命令，渲染模板。"""
        if not isinstance(run, dict):
            return ""
        for _, c in run.items():
            return self.r(c)
        return ""

    def _cautions(self, n):
        for c in n.get("cautions", []) or []:
            self.io._p(f"  ⚠ {self.r(c)}")

    def _parse_into_ctx(self, node, stdout):
        pfn = parsers.get_parser(node["parser"]) if node.get("parser") else None
        out = pfn(stdout) if pfn else run_sim._default_parse(stdout)
        if not isinstance(out, dict):
            out = {"rows": out}
        # 节点标量并入 output.*（§7.6c）与裸命名空间
        scalar_ns = {k: v for k, v in out.items() if k not in ("rows", "lines")}
        self.ctx.update(out)
        self.ctx["output"] = {**self.ctx.get("output", {}), **scalar_ns,
                              **(out.get("output") if isinstance(out.get("output"), dict) else {})}
        self.ctx.setdefault("lines", stdout.splitlines())

    def _eval_branch(self, n):
        for br in n.get("branch", []):
            try:
                if exprlang._truthy(exprlang.evaluate(br["when"], self.ctx)):
                    return br["goto"]
            except exprlang.EvalError:
                pass
        return n.get("otherwise", "escalate")

    # ---- 节点处理 ----
    def _do_check(self, n):
        self.io._p(f"\n━━ [排查] {self.r(n.get('title',''))} ━━")
        self._cautions(n)
        cmd = self._cmd_for(n.get("run"))
        if self.mode == "real" and run_sim._is_readonly(cmd):
            import subprocess
            self.io._p(f"▶ 自动执行(只读)：{cmd}")
            try:
                stdout = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=15).stdout
            except Exception as e:
                stdout = ""
                self.io._p(f"  命令异常：{e}")
        else:
            stdout = self.io.paste(n["id"], f"▶ 请执行并粘贴输出（END 结束）：\n  $ {cmd}")
        self._parse_into_ctx(n, stdout)
        nxt = self._eval_branch(n)
        self.io._p(f"→ 判读结果：转 {nxt}")
        self._log(n["id"], "check", cmd=cmd, next=nxt, output=self._summ(stdout))
        return nxt

    def _do_ask(self, n):
        self.io._p(f"\n━━ [选择] {self.r(n.get('title',''))} ━━")
        self.io._p(self.r(n["question"]))
        idx = self.io.choose(n["id"], "", n["options"])
        opt = n["options"][idx]
        if n.get("binds"):
            self.ctx[n["binds"]] = opt["label"]
        self._log(n["id"], "ask", chose=opt["label"], next=opt["goto"])
        return opt["goto"]

    def _do_action(self, n):
        risk = n.get("risk", "?")
        self.io._p(f"\n━━ [变更] {self.r(n.get('title',''))} ━━  风险: {risk}")
        pf = n.get("preflight")
        if pf:
            self.io._p("📋 变更简报（Pre-flight Brief）")
            self.io._p(f"  影响面: {self.r(pf.get('blast_radius',''))}")
            if pf.get("est_downtime"):
                self.io._p(f"  预估停机: {self.r(pf['est_downtime'])}")
            self.io._p("  执行中盯这些指标:")
            for w in pf.get("watch", []):
                self.io._p(f"    · {self._cmd_for(w.get('run'))}  → 期望: {self.r(w.get('expect',''))}")
            self.io._p("  什么情况立即中止:")
            for a in pf.get("abort_if", []):
                self.io._p(f"    · {self.r(a)}")
        rb = n.get("rollback", {})
        self.io._p("  ── 将要执行的命令（导航档：请你亲自执行，Agent 不代执行）──")
        self.io._p(f"    $ {self._cmd_for(n.get('run'))}")
        if rb.get("advisory"):
            self.io._p(f"  ── 回滚（人工指引，{rb.get('type')}）──  非可执行命令，见 cautions")
        else:
            self.io._p(f"  ── 回滚方案（{rb.get('type')}）──")
            if rb.get("type") == "snapshot" and rb.get("snapshot"):
                self.io._p(f"    先快照: $ {self._cmd_for(rb['snapshot'].get('run'))}")
            self.io._p(f"    $ {self._cmd_for(rb.get('run'))}")
        self._cautions(n)
        if n.get("human_only"):
            self.io._p("  ⛔ human_only：此步骤 Agent 任何档位都不执行，仅出指导。")
        decision = self.io.action_decision(n["id"], "需要审批。你的决定？")
        if decision != "proceed":
            self._log(n["id"], "action", risk=risk, decision=decision)
            if decision == "skip":
                nxt = n.get("goto", "escalate")
                self.io._p(f"→ 跳过此变更（未执行），继续：转 {nxt}。")
                return nxt
            if decision == "quit":
                self.io._p("→ 退出会话（进度已保存，可 --resume 续跑）。")
                return "__quit__"
            self.io._p("→ 升级人工。")
            return "escalate"
        # verify 指导
        v = n.get("verify", {})
        vcmd = self._cmd_for(v.get("run"))
        stdout = self.io.paste(n["id"] + ":verify", f"执行完成后，粘贴 verify 输出判定结果（END 结束）：\n  $ {vcmd}")
        if v.get("parser"):
            self._parse_into_ctx({"parser": v["parser"]}, stdout)
        passed = False
        try:
            passed = exprlang._truthy(exprlang.evaluate(v.get("assert", "false"), self.ctx))
        except exprlang.EvalError:
            passed = False
        self._log(n["id"], "action", risk=risk, decision="proceed",
                  verify_passed=passed, verify_output=self._summ(stdout))
        if passed:
            self.io._p("→ verify 通过。")
            return n.get("goto", "escalate")
        self.io._p(f"→ verify 未过，on_fail={v.get('on_fail')}。")
        return "rollback_guide" if v.get("on_fail") == "rollback" else "escalate"

    def _do_terminal(self, n):
        kind = n["type"]
        icon = "✅" if kind == "done" else "⏫"
        self.io._p(f"\n━━ {icon} {'结论' if kind=='done' else '升级人工'} ━━")
        self.io._p(self.r(n.get("summary", "")))
        self.outcome = kind
        # 单比特反馈 + attest 提示
        ans = ""
        fb = self.skill.get("feedback", {}).get("ask")
        if fb:
            self.io._p(f"\n{fb} 👍/👎")
            if self.io.answers is not None:
                ans = self.io.paste(n["id"] + ":fb", "").strip()
            else:
                try:
                    ans = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    ans = ""
            self._log(n["id"], "feedback", answer=ans)
        # V-3/W-3：一键认证——仅 done 才追问，outcome 结合反馈
        if kind == "done":
            self._offer_attest(n, feedback=ans)

    @staticmethod
    def _outcome_from_feedback(fb):
        """👎/否定反馈 → partial（负面 attestation 同样是宝贵信号，docs/05 允许）。"""
        neg = ("👎", "no", "n", "否", "没", "未解决", "不行", "没解决")
        return "partial" if fb and any(t in fb.lower() for t in neg) else "resolved"

    def _offer_attest(self, n, feedback=""):
        """run 终点接单：确认→从会话预填→只补 2 个分桶→签名落盘（docs/08 §2）。"""
        info = self.io.attest_intake(n["id"], "要把这次验证沉淀为社区凭据吗？")
        if not info:
            self.io._p("（可稍后：opsaxiom attest --from-session %s）" % self.sid)
            return
        rollback = "rollback_guide" in self.path
        mode = {"guided": "navigator", "real": "copilot"}.get(self.mode, "navigator")
        # W-3：outcome 结合反馈；intake 显式给了 outcome 则以它为准
        outcome = info.get("outcome") or self._outcome_from_feedback(feedback)
        if outcome == "partial":
            self.io._p("  （按你的反馈记为 partial——负面记录同样帮助社区改进这个 Skill）")
        attest_bin = str(HERE / "bin" / "opsaxiom-attest")
        cmd = [sys.executable, attest_bin,
               "--skill", self.skill["metadata"]["id"],
               "--skill-version", str(self.skill["metadata"].get("version", "0.1.0")),
               "--outcome", outcome, "--mode", mode,
               "--os-family", str(info.get("os_family", "linux")),
               "--scale", str(info.get("scale", "1")),
               "--attestor", str(info.get("attestor", "anonymous"))]
        if rollback:
            cmd.append("--rollback-exercised")
        import subprocess
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.io._p(r.stdout.strip() or r.stderr.strip())
        self._log(n["id"], "attest", ok=(r.returncode == 0))

    def run(self, start=None):
        node, guard = (start or self.entry), 0
        if not self.path:
            self.path = [node]
        while guard < 80:
            guard += 1
            self._write_state(node)          # 每步落状态，供 --resume
            n = self.nodes.get(node)
            if n is None:
                if node == "__quit__":
                    self.outcome = "quit"
                    break
                if node == "rollback_guide":
                    self.io._p("请按上方回滚方案执行回滚，然后重新评估。")
                    self.outcome = "rolled_back"
                    break
                if node in ("escalate", "done"):
                    self.io._p(f"\n━━ {node} ━━")
                    self.outcome = node
                    break
                self.io._p(f"[异常] 未知节点 {node}")
                break
            t = n["type"]
            if t == "check":
                node = self._do_check(n)
            elif t == "ask":
                node = self._do_ask(n)
            elif t == "action":
                node = self._do_action(n)
            elif t in ("done", "escalate"):
                self._do_terminal(n)
                break
            else:
                break
            self.path.append(node)
        # 结束态：清理续跑状态；中途退出则保留
        f = self._write_audit()
        sf = self._sess_dir() / f"{self.sid}.state.json"
        if self.outcome in ("done", "escalate", "rolled_back") and sf.exists():
            sf.unlink()
        # meta.json 留存供 attest --from-session 预填（不随 state 清理）
        (self._sess_dir() / f"{self.sid}.meta.json").write_text(json.dumps(
            {"skill_id": self.skill["metadata"]["id"], "mode": self.mode,
             "path": self.path, "outcome": self.outcome}, ensure_ascii=False), encoding="utf-8")
        return {"path": self.path, "outcome": self.outcome, "audit_file": str(f)}
