"""
gate.py —— 执行门（docs/12 §4，I-1）。远程命令的【唯一】入口。

一条命令要打到远端，必须穿过这道门，顺序不可调换：
  1. 目标存在（load_targets，access 三红线已在加载时把关）
  2. 已授权（per-target trust；I-2 升级为 TTL）——未授权直接拒
  3. 只读白名单（按 connector：ssh/kubectl 走 _is_readonly；network/http 见 I-5）
     —— 写命令结构性进不来（R-A3）
  4. param 注入防护（T-3：不可信 param 值含 shell 元字符且出现在命令里 → 拒）
  5. 解析凭证（access.resolve）→ 连接器执行
  6. 审计落盘（命令/输出摘要/目标/时刻；【绝不】写凭证——R-A2）

连接器只负责"拨通"，不做任何安全判断——安全全在这道门里（docs/12 §4）。
拒绝也审计：一次被拦的写命令是安全事件，要留痕。
"""
import datetime
import hashlib
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "sim"))
import access          # noqa: E402
import sweep           # noqa: E402
from run_sim import _is_readonly  # noqa: E402


class GateError(Exception):
    pass


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


def _audit_file():
    return _home() / "audit" / "remote.jsonl"


def is_authorized(target_name):
    """per-target 授权检查。I-1 复用 sweep.is_trusted（auto_exec 列表）；
    I-2 升级为带 TTL 的结构，此函数签名不变。"""
    return sweep.is_trusted(target_name)


def _readonly_ok(connector, cmd):
    """按 connector 类型判只读。ssh/kubectl 复用 _is_readonly（同一套白名单）。"""
    if connector in ("ssh", "kubectl"):
        return _is_readonly(cmd)
    if connector in ("network", "http"):
        # I-5 接线；在此之前这两类不放行，避免出现"未过白名单就执行"
        raise GateError(f"connector={connector} 的只读闸门尚未接线（见 TODO I-5）")
    raise GateError(f"未知 connector：{connector}")


def _audit(record):
    f = _audit_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _stamp(now=None):
    # 允许注入 now（Date.now 在某些环境不可用/测试需确定性）
    if now is not None:
        return now
    return datetime.datetime.now().isoformat(timespec="seconds")


def run_remote(target_name, cmd, *, params=None, targets=None,
               connector_fn=None, now=None):
    """把一条只读命令打到远端目标，返回 stdout。任何一关不过 → GateError（并审计）。

    connector_fn: 便于测试注入的连接器 (target, cred, cmd) -> (rc, out, err)；
                  默认按 target.connector 选真实连接器。
    """
    targets = access.load_targets() if targets is None else targets
    if target_name not in targets:
        raise GateError(f"未知目标：{target_name}（先 opsaxiom target add {target_name}）")
    t = dict(targets[target_name]); t.setdefault("name", target_name)
    conn = t.get("connector")

    def deny(reason):
        _audit({"ts": _stamp(now), "target": target_name, "host": t.get("host"),
                "connector": conn, "cmd": cmd, "decision": "deny", "reason": reason})
        raise GateError(reason)

    # 2. 授权
    if not is_authorized(target_name):
        deny(f"目标 {target_name} 未授权自动执行——先 opsaxiom target grant {target_name}")
    # 3. 只读白名单
    try:
        ok = _readonly_ok(conn, cmd)
    except GateError as e:
        deny(str(e))
    if not ok:
        deny(f"写/非只读命令被执行门拒绝：{cmd!r}")
    # 4. T-3 param 注入防护（不可信 param 值含元字符且出现在命令里）
    if params:
        for bad in sweep.unsafe_values(params):
            if bad in cmd:
                deny(f"param 注入被拒（值含 shell 元字符）：{bad!r}")
    # 5. 解析凭证 + 执行
    cred = access.resolve(t)
    fn = connector_fn or _default_connector(conn)
    rc, out, err = fn(t, cred, cmd)
    # 6. 审计（凭证绝不入审计——只记 kind，不记材料）
    _audit({"ts": _stamp(now), "target": target_name, "host": t.get("host"),
            "connector": conn, "cmd": cmd, "decision": "allow",
            "cred_kind": cred.kind, "exit": rc,
            "out_sha256": hashlib.sha256(out.encode("utf-8", "replace")).hexdigest()[:16],
            "out_bytes": len(out)})
    if rc != 0 and not out:
        raise GateError(f"远端执行返回码 {rc}：{err.strip()[:200]}")
    return out


def _default_connector(connector):
    if connector == "ssh":
        from connectors import ssh_conn
        return ssh_conn.exec_readonly
    raise GateError(f"connector={connector} 尚无真实实现（见 TODO I-5）")
