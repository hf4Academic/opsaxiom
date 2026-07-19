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


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


# ---------- 纯逻辑（可单测，不碰 IO/交互）----------

def parse_ssh_config(text):
    """解析 ~/.ssh/config，产出可导入的 target 条目。跳过含通配符的 Host（*/?）。"""
    out = []
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition(" ")
        key = key.lower(); val = val.strip()
        if key == "host":
            for name in val.split():
                if "*" in name or "?" in name:      # 通配符条目跳过（不是具体设备）
                    cur = None; continue
                cur = {"name": name, "connector": "ssh", "auth": "ssh_config"}
                out.append(cur)
        elif cur is not None:
            if key == "hostname":
                cur["host"] = val
            elif key == "user":
                cur["user"] = val
            elif key == "port":
                cur["port"] = int(val) if val.isdigit() else val
            elif key == "proxyjump":
                cur["reach"] = "jump:" + val.split(",")[0].strip()
    # 去掉只有通配符段落里冒出来的空条目
    return [t for t in out if t.get("name")]


def build_target_entry(connector, host=None, auth=None, user=None,
                       port=None, reach=None, context=None):
    """从向导答案组装 target 条目（不含 name）。auth 缺省按 connector 给合理引用。"""
    t = {"connector": connector}
    if auth is None:
        auth = {"ssh": "ssh_config", "network": None,
                "kubectl": "kubeconfig", "http": None}.get(connector)
    if auth:
        t["auth"] = auth
    if host:
        t["host"] = host
    if user:
        t["user"] = user
    if port:
        t["port"] = port
    if reach:
        t["reach"] = reach
    if context:
        t["context"] = context
    return t


def detect_default_auth(host, ssh_config_text=None, agent_has_keys=False):
    """自动试探默认 auth：config 里有该 Host 条目→ssh_config；agent 有钥匙→agent。"""
    if ssh_config_text:
        for t in parse_ssh_config(ssh_config_text):
            if t["name"] == host:
                return "ssh_config"
    return "agent" if agent_has_keys else "ssh_config"


def diagnose_reach(rows):
    """给 doctor 的逐目标结果做 reach 分组诊断（docs/12 §4.5）。
    rows: [{target, reach, reachable}]；返回 [提示串]。
    同一 reach 标签下的目标【全部】不可达 → 判为网络前置未就绪，而非逐台报错。"""
    groups = {}
    for r in rows:
        if r.get("reach"):
            groups.setdefault(r["reach"], []).append(r)
    hints = []
    for tag, members in groups.items():
        if all(not m["reachable"] for m in members):
            kind, _, name = tag.partition(":")
            what = {"vpn": "VPN", "jump": "跳板"}.get(kind, kind)
            hints.append(f"⚠ {tag} 下 {len(members)} 个目标全部不可达——"
                         f"疑似{what}『{name}』未就绪（先连上再重试），而非这些设备都挂了")
    return hints


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


def _save_targets(targets):
    f = _home() / "targets.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    f.write_text(yaml.safe_dump({"targets": targets}, allow_unicode=True), encoding="utf-8")
    # 存完立即回读校验（走 access 三红线），有问题当场暴露
    access.load_targets(f)
    return f


def _cmd_add(args):
    try:
        targets = access.load_targets()
    except access.AccessError as e:
        print(e); return 1
    if args.name in targets:
        print(f"{args.name} 已存在。"); return 1
    cfg_path = pathlib.Path.home() / ".ssh" / "config"
    cfg_text = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
    agent_has = bool(os.environ.get("SSH_AUTH_SOCK"))

    def ask(prompt, default=""):
        v = input(f"{prompt}" + (f"（{default}）" if default else "") + "：").strip()
        return v or default

    conn = ask("连接方式 [ssh/network/kubectl/http]", "ssh")
    entry = {}
    if conn == "kubectl":
        entry = build_target_entry("kubectl", auth="kubeconfig",
                                   context=ask("kube context（留空=当前）") or None)
    else:
        host = ask("主机地址（IP/域名）")
        auth = detect_default_auth(host, cfg_text, agent_has) if conn == "ssh" else \
            ("keyring:" + args.name)
        entry = build_target_entry(conn, host=host, auth=auth,
                                   user=(ask("登录用户") or None) if conn != "http" else None)
    reach = ask("需要先连 VPN/跳板吗？填标签如 vpn:office（留空=直连）")
    if reach:
        entry["reach"] = reach
    targets[args.name] = entry
    try:
        _save_targets(targets)
    except access.AccessError as e:
        print(f"✘ {e}"); return 1
    print(f"✔ 已添加 {args.name}（凭证用引用 {entry.get('auth','-')}，不保存任何密码）。"
          f"授权自动执行：opsaxiom target grant {args.name}")
    return 0


def _cmd_import(args):
    cfg = pathlib.Path.home() / ".ssh" / "config"
    if not cfg.exists():
        print("没有 ~/.ssh/config，无法导入。"); return 1
    cands = parse_ssh_config(cfg.read_text(encoding="utf-8"))
    try:
        targets = access.load_targets()
    except access.AccessError as e:
        print(e); return 1
    new = [c for c in cands if c["name"] not in targets]
    if not new:
        print("没有可导入的新条目（通配符 Host 已跳过）。"); return 0
    print("将导入以下设备（凭证仍走你现有的 ssh 配置，此处只存引用）：")
    for c in new:
        print(f"  {c['name']:<16} {c.get('host', c['name'])}  "
              f"{'via ' + c['reach'] if c.get('reach') else ''}")
    if input("确认导入？[y/N] ").strip().lower() != "y":
        print("已取消。"); return 0
    for c in new:
        name = c.pop("name")
        targets[name] = c
    _save_targets(targets)
    print(f"✔ 已导入 {len(new)} 台。逐台授权：opsaxiom target grant <名字>")
    return 0


def _default_probe(name, t, timeout=3):
    """默认可达性探针：TCP 连通 + 凭证可解析。权限检测留给真实连接（此处不强连）。"""
    import socket
    reachable = False
    host, port = t.get("host"), int(t.get("port", 22 if t.get("connector") == "ssh" else 0))
    if host and port:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                reachable = True
        except OSError:
            reachable = False
    elif t.get("connector") == "kubectl":
        reachable = True                     # kubectl 走本机 kubeconfig，连通性交给 kubectl
    cred_ok, cred_msg = True, ""
    try:
        access.resolve(t)
    except access.AccessError as e:
        cred_ok, cred_msg = False, str(e)
    return {"reachable": reachable, "cred_ok": cred_ok, "cred_msg": cred_msg}


def _cmd_doctor(args, probe=None):
    probe = probe or _default_probe
    try:
        targets = access.load_targets()
    except access.AccessError as e:
        print(e); return 1
    if not targets:
        print("尚无设备。"); return 0
    rows = []
    for name, t in targets.items():
        r = probe(name, t)
        if not r["reachable"]:
            light = "🔴"; note = "连不上"
        elif not r["cred_ok"]:
            light = "🟡"; note = r.get("cred_msg", "凭证待配")
        else:
            light = "🟢"; note = "可达 · 凭证就绪"
        print(f"{light} {name:<16} {note}")
        rows.append({"target": name, "reach": t.get("reach"), "reachable": r["reachable"]})
    for hint in diagnose_reach(rows):
        print(hint)
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

    a = ts.add_parser("add", help="添加一台设备（交互向导）")
    a.add_argument("name")
    a.set_defaults(fn=_cmd_add)

    ts.add_parser("import-ssh-config",
                  help="从 ~/.ssh/config 批量导入").set_defaults(fn=_cmd_import)

    ts.add_parser("doctor", help="逐目标体检：连通/凭证/reach 分组诊断"
                  ).set_defaults(fn=_cmd_doctor)
