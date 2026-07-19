"""V-2 CLI 接线：opsaxiom skill ... / opsaxiom record ...（挂到主 CLI）。"""
import json
import os
import pathlib
import sys

import capture


def _sessions_dir():
    return pathlib.Path(os.environ.get(
        "OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom")) / "sessions"


def list_sessions(limit=10):
    """最近的排查会话（新→旧）：sid/时间/skill/结局。供选择器与缺省 sid。"""
    d = _sessions_dir()
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        sid = f.stem
        meta = {}
        mf = d / f"{sid}.meta.json"
        if mf.exists():
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                pass
        out.append({"sid": sid, "mtime": int(f.stat().st_mtime),
                    "skill_id": meta.get("skill_id", ""),
                    "outcome": meta.get("outcome", "")})
    return out


def _cmd_skill(args):
    sub = args.skill_cmd
    if sub == "sessions":
        rows = list_sessions(limit=args.limit)
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['sid']}  {r['skill_id'] or '(record)'}  {r['outcome'] or '-'}")
        return 0
    if sub == "from-session":
        sid = args.sid
        if not sid:                       # 缺省 = 最近一次排查会话（发起人验收：免记 sid）
            rows = list_sessions(limit=1)
            if not rows:
                print("没有任何排查会话。先排查一次，或 opsaxiom record start 录一段。")
                return 1
            sid = rows[0]["sid"]
            print(f"（未指定会话，自动取最近一次：{sid}）")
        sf = capture.from_session(sid, args.id, args.name, args.taxonomy)
        print(f"已生成草稿：{sf}")
        print("下一步：opsaxiom skill lint " + str(sf) + "  然后补全 TODO（分支表达式/cautions/结论）")
        return 0
    if sub == "new":
        if getattr(args, "spec_json", False):
            # pi TUI 多轮对话收集好答案后经 stdin 传 spec（同一构建逻辑，不复制）
            spec = json.loads(sys.stdin.read())
            sf = capture.wizard_from_spec(spec)
        else:
            sf = capture.wizard()
        print(f"已生成草稿：{sf}")
        print("下一步：opsaxiom skill lint " + str(sf))
        return 0
    if sub == "lint":
        rep, gaps = capture.lint(args.path)
        rep.print()
        if gaps:
            print("\n缺口清单（补全后即可走仿真晋级）：")
            for g in gaps:
                print(f"  · {g}")
        else:
            print("\n无缺口，可写 sim 场景并 promote。")
        return 1 if rep.errors or gaps else 0
    if sub == "fork":
        import localskill
        import incident as I
        bp, base = I.load_skill_by_id(args.base_id)
        if not base:
            print(f"找不到基线 Skill：{args.base_id}"); return 1
        try:
            sf = localskill.fork(base, bp)
        except localskill.LocalSkillError as e:
            print(f"✘ {e}"); return 1
        print(f"✔ 已派生本地 fork：{sf}")
        print(f"  id={base['metadata']['id']} → local.{base['metadata']['id']}"
              f"（visibility:local，徽章清零；本地改完走 validate/promote，永不出门）")
        return 0
    if sub == "doctor":
        return _cmd_skill_doctor(args)
    return 2


def _cmd_skill_doctor(args):
    """skill doctor：体检个人层——overlay 失配节点、fork 落后基线。"""
    import localskill
    import overlay
    import yaml
    from incident import load_skill_by_id
    issues = 0
    # ① overlay 体检：引用了不存在的节点 → 黄牌（不阻塞，但要清理）
    ov_dir = overlay.overlay_path("x").parent
    if ov_dir.is_dir():
        for f in sorted(ov_dir.glob("*.yaml")):
            sid = f.stem
            try:
                ov = overlay.load(sid, path=f)
            except overlay.OverlayError as e:
                print(f"🟡 {sid}: overlay 违规未加载（{e}）"); issues += 1; continue
            if not ov:
                continue
            _, base = load_skill_by_id(ov.get("base", sid))
            if not base:
                print(f"🟡 {sid}: overlay 的基线 Skill 不在库中（{ov.get('base')}）"); issues += 1
                continue
            missing = overlay.unmatched_nodes(ov, base)
            if missing:
                print(f"🟡 {sid}: overlay 引用了已消失节点 {missing}（基线可能已升级，请核对）")
                issues += 1
    # ② fork 体检：落后基线版本 → 提示合并
    for f in localskill.skills_local_dir().rglob("skill.yaml") if localskill.skills_local_dir().is_dir() else []:
        m = yaml.safe_load(f.read_text(encoding="utf-8"))["metadata"]
        derived = m.get("derived_from")
        if derived:
            base_id = derived.split("@")[0]
            _, base = load_skill_by_id(base_id)
            if base:
                from_ver = derived.split("@", 1)[-1]
                cur_ver = base["metadata"].get("version", "?")
                if cur_ver != from_ver:
                    print(f"🟡 {m['id']}: 基线已出 {cur_ver}，fork 基于 {from_ver}——"
                          f"用 git diff 看 {base_id} 的变更后人工合并")
                    issues += 1
    print(f"{'🟢 个人层健康' if issues == 0 else f'发现 {issues} 处需注意'}")
    return 0 if issues == 0 else 1


def _cmd_record(args):
    sub = args.record_cmd
    if sub == "start":
        sid = capture.record_start(args.name)
        print(f"记录会话已开始：{sid}。用 record exec <只读命令> 或 record note 投喂步骤，record stop 结束。")
        return 0
    if sub == "exec":
        step, summ = capture.record_exec(" ".join(args.cmd))
        print(f"[{step}] 已记录：{summ[:80]}")
        return 0
    if sub == "note":
        step = capture.record_note(args.cmd, sys.stdin.read())
        print(f"[{step}] 已记录（手工投喂）")
        return 0
    if sub == "stop":
        sid = capture.record_stop()
        print(f"记录结束：{sid}。转成草稿：opsaxiom skill from-session {sid} --id <域.xxx> --name <名> --taxonomy <域/xxx>")
        return 0
    return 2


def add_capture(subparsers):
    sp = subparsers.add_parser("skill", help="经验捕获：把排查变成 Skill 草稿")
    ssub = sp.add_subparsers(dest="skill_cmd", required=True)
    se = ssub.add_parser("sessions", help="列最近的排查会话（供 from-session 选）")
    se.add_argument("--limit", type=int, default=10)
    se.add_argument("--json", action="store_true")
    fs = ssub.add_parser("from-session", help="从导航档会话审计生成草稿")
    fs.add_argument("sid", nargs="?", default=None, help="缺省=最近一次会话")
    fs.add_argument("--id", required=True, help="Skill id，如 host.process.foo")
    fs.add_argument("--name", required=True)
    fs.add_argument("--taxonomy", required=True, help="如 host/process/foo")
    ne = ssub.add_parser("new", help="向导式从零生成草稿")
    ne.add_argument("--spec-json", dest="spec_json", action="store_true",
                    help="从 stdin 读 JSON spec（pi TUI 对话流用）")
    ln = ssub.add_parser("lint", help="校验草稿并列出缺口")
    ln.add_argument("path")
    fk = ssub.add_parser("fork", help="从通用 Skill 派生本地个性化版本（永不出门）")
    fk.add_argument("base_id", help="基线 Skill id，如 middleware.es.disk-watermark")
    dc = ssub.add_parser("doctor", help="体检个人层：overlay 失配 / fork 落后基线")
    dc.add_argument("--json", action="store_true")
    sp.set_defaults(fn=_cmd_skill)

    rp = subparsers.add_parser("record", help="记录一次没走 Skill 的排查")
    rsub = rp.add_subparsers(dest="record_cmd", required=True)
    rsub.add_parser("start").add_argument("name")
    ex = rsub.add_parser("exec", help="代跑只读命令并留痕")
    ex.add_argument("cmd", nargs="+")
    nt = rsub.add_parser("note", help="手工投喂一步：note <命令>，输出从 stdin 读")
    nt.add_argument("cmd")
    rsub.add_parser("stop")
    rp.set_defaults(fn=_cmd_record)
