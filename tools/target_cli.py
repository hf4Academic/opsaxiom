"""
target_cli.py —— `opsaxiom target ...` 子命令（I-2 授权/清单，I-3 add/import/doctor）。

设备接入的用户入口。安全约束见 docs/12；凭证永不经此存储（只存引用）。
"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "sim"))
import access          # noqa: E402
import sweep           # noqa: E402


def _fmt_remaining(rem):
    if rem is None:
        return "永久"
    if rem <= 0:
        return "已过期"
    return f"剩 {rem:.0f} 天"


def _cmd_list(args):
    try:
        targets = access.load_targets()
    except access.AccessError as e:
        print(e); return 1
    grants = {g["target"]: g for g in sweep.list_grants()}
    if not targets:
        print("尚无设备。用 opsaxiom target add <名字> 添加。"); return 0
    print(f"{'目标':<16} {'连接器':<9} {'主机':<18} {'授权':<10} reach")
    for name, t in targets.items():
        g = grants.get(name)
        auth = _fmt_remaining(g["remaining_days"]) if g else "未授权"
        print(f"{name:<16} {t.get('connector',''):<9} {str(t.get('host','')):<18} "
              f"{auth:<10} {t.get('reach','') or ''}")
    return 0


def _cmd_grant(args):
    try:
        targets = access.load_targets()
    except access.AccessError as e:
        print(e); return 1
    if args.name not in targets:
        print(f"未知目标：{args.name}（先 opsaxiom target add {args.name}）"); return 1
    sweep.grant_trust(args.name, ttl_days=args.ttl_days, scope="readonly")
    print(f"✔ 已授权 {args.name} 自动执行只读命令（{args.ttl_days} 天后到期，"
          f"opsaxiom target revoke {args.name} 可随时收回）")
    return 0


def _cmd_revoke(args):
    if sweep.revoke_trust(args.name):
        print(f"✔ 已收回 {args.name} 的授权。")
    else:
        print(f"{args.name} 本就没有授权，无需收回。")
    return 0


def add_target(subparsers):
    tp = subparsers.add_parser("target", help="接入你的设备（清单只存引用，凭证不出本机）")
    ts = tp.add_subparsers(dest="target_cmd", required=True)

    ts.add_parser("list", help="列出设备与授权状态").set_defaults(fn=_cmd_list)

    g = ts.add_parser("grant", help="授权某目标自动执行只读命令（带 TTL）")
    g.add_argument("name")
    g.add_argument("--ttl-days", type=int, default=30, dest="ttl_days")
    g.set_defaults(fn=_cmd_grant)

    r = ts.add_parser("revoke", help="收回某目标的授权")
    r.add_argument("name")
    r.set_defaults(fn=_cmd_revoke)
