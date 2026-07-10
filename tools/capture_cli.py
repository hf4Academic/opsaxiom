"""V-2 CLI 接线：opsaxiom skill ... / opsaxiom record ...（挂到主 CLI）。"""
import sys

import capture


def _cmd_skill(args):
    sub = args.skill_cmd
    if sub == "from-session":
        sf = capture.from_session(args.sid, args.id, args.name, args.taxonomy)
        print(f"已生成草稿：{sf}")
        print("下一步：opsaxiom skill lint " + str(sf) + "  然后补全 TODO（分支表达式/cautions/结论）")
        return 0
    if sub == "new":
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
    return 2


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
    fs = ssub.add_parser("from-session", help="从导航档会话审计生成草稿")
    fs.add_argument("sid")
    fs.add_argument("--id", required=True, help="Skill id，如 host.process.foo")
    fs.add_argument("--name", required=True)
    fs.add_argument("--taxonomy", required=True, help="如 host/process/foo")
    ne = ssub.add_parser("new", help="向导式从零生成草稿")
    ln = ssub.add_parser("lint", help="校验草稿并列出缺口")
    ln.add_argument("path")
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
