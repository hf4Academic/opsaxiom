"""cred_cli.py —— `opsaxiom cred ...` 子命令（I-6）。凭证只进钥匙串/加密文件与内存。"""
import getpass
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cred  # noqa: E402


def _cmd_set(args):
    fields = {}
    if args.username:
        fields["username"] = args.username
    secret = {}
    val = getpass.getpass(f"凭证值（{args.name} 的密码/token，不回显）：")
    if not val:
        print("✘ 空值未保存"); return 1
    secret["password"] = val
    backend = cred.set_cred(args.name, {**fields, **secret})
    print(f"✔ 已存 {args.name}（后端={backend}；值不在文件里明文，cred list 只显示名）")
    return 0


def _cmd_rm(args):
    print(f"{'✔ 已删除' if cred.rm_cred(args.name) else f'{args.name} 不存在'}。")
    return 0


def _cmd_list(args):
    rows = cred.list_creds()
    if not rows:
        print("暂无凭证。opsaxiom cred set <名字> 存一条。"); return 0
    print("凭证条目（只显示名字与字段名，值绝不回显）：")
    for r in rows:
        print(f"  {r['name']:<16} 字段: {', '.join(r['fields'])}")
    return 0


def add_cred(subparsers):
    cp = subparsers.add_parser("cred", help="本地凭证管理（值存钥匙串/加密文件，绝不回显）")
    cs = cp.add_subparsers(dest="cred_cmd", required=True)
    s = cs.add_parser("set", help="存一条凭证（交互输入值，不回显）")
    s.add_argument("name")
    s.add_argument("--username", "-u", default=None, help="关联用户名（如网络设备账号）")
    s.set_defaults(fn=_cmd_set)
    r = cs.add_parser("rm", help="删除一条凭证")
    r.add_argument("name")
    r.set_defaults(fn=_cmd_rm)
    cs.add_parser("list", help="列出凭证名（不显示值）").set_defaults(fn=_cmd_list)
