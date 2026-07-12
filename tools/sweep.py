"""
批量取证执行（Z-3，docs/09 §1.2）。

把 evidence.build_plan 产出的取证计划变成事实：
- **本机协驾**：auto 探针自动执行（执行时二次校验 _is_readonly + T-3 参数注入防护），
  解析入事实库。首次本机自动执行需一次性授权，记 trust.yaml。
- **导航档 / 远端**：渲染成【一个】粘贴块（nonce 分隔符），人跑一次贴回；
  或 `collect` 出自包含脚本、`ingest` 回灌。回合数从 O(节点) 降到 O(1 粘贴)。

三条对抗纪律（docs/09 §6，均带测试）：
1. 分隔符伪造：贴回文本里伪造的边界不带会话 nonce → 判为数据，不切段。
2. 参数注入（T-3）：param 值含 shell 元字符 → 拒绝自动执行该探针（模板作者可信、
   param 值来自告警/人不可信；模板自带的管道不受影响，只查 param 值）。
3. 白名单外命令绝不自动执行：auto 由 Z-2 依 _is_readonly 判，执行时再校验一次。
"""
import pathlib
import re
import secrets
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim"))
import parsers          # noqa: E402
import yaml             # noqa: E402
from run_sim import _is_readonly, _default_parse  # noqa: E402
from facts import LOCAL  # noqa: E402

# param 值里出现即视为注入企图的 shell 元字符（命令链接/替换/重定向/换行）。
# 注意：只查 param 的【值】，不查整条命令——模板自带的管道(dmesg|grep)是可信的。
_META_VAL = re.compile(r"[;&|`$<>(){}\n]")


def is_shell_safe(value):
    return not _META_VAL.search(str(value))


def unsafe_values(params):
    """params 里不安全的值集合（供执行时比对：命令含此值即拒自动执行）。"""
    return {str(v) for v in params.values() if not is_shell_safe(v)}


def flatten(plan):
    """按波次顺序展开去重后的探针，附全局 index（供 nonce 段映射）。"""
    out = []
    for w in plan["waves"]:
        for p in w["probes"]:
            q = dict(p)
            q["index"] = len(out)
            out.append(q)
    return out


# ---------- 解析入库（复用确定性解析器，R9）----------
def _parse(cmd, parser, stdout):
    pfn = None
    if parser and "{{" not in parser:      # 模板化 parser 名未定→退默认解析
        pfn = parsers.get_parser(parser)
    out = pfn(stdout) if pfn else _default_parse(stdout)
    if not isinstance(out, dict):
        out = {"rows": out}
    out.setdefault("lines", stdout.splitlines())
    return out


def _store_result(store, probe, stdout, now):
    parsed = _parse(probe["cmd"], probe.get("parser"), stdout)
    store.put_parsed(probe["cmd"], parsed, target=probe.get("target", LOCAL),
                     parser=probe.get("parser"), now=now)
    return parsed


# ---------- 本机协驾：自动执行 ----------
def _default_runner(cmd, timeout=15):
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                       timeout=timeout)
    return r.stdout


def execute_auto(plan, params, store, now=None, runner=None):
    """自动执行 auto 探针（本机只读），解析入库。返回执行报告列表。

    每条报告：{node, cmd, status, fields?}。status ∈
      executed / blocked-injection / blocked-not-readonly / not-auto / error。
    runner 可注入（测试用），默认真实 bash -c。
    """
    runner = runner or _default_runner
    bad = unsafe_values(params)
    report = []
    for p in flatten(plan):
        if not p["auto"]:
            report.append({"node": p["node"], "cmd": p["cmd"], "status": "not-auto"})
            continue
        # 对抗①：param 注入——命令含任一不安全 param 值 → 拒（T-3）
        if any(v in p["cmd"] for v in bad):
            report.append({"node": p["node"], "cmd": p["cmd"],
                           "status": "blocked-injection"})
            continue
        # 对抗②：执行时二次校验只读（纵深防御，防计划被篡改）
        if not _is_readonly(p["cmd"]):
            report.append({"node": p["node"], "cmd": p["cmd"],
                           "status": "blocked-not-readonly"})
            continue
        try:
            stdout = runner(p["cmd"])
        except Exception as e:                       # noqa: BLE001
            report.append({"node": p["node"], "cmd": p["cmd"],
                           "status": "error", "err": str(e)})
            continue
        parsed = _store_result(store, p, stdout, now)
        report.append({"node": p["node"], "cmd": p["cmd"], "status": "executed",
                       "fields": [k for k in parsed if k not in ("rows", "lines")]})
    return report


# ---------- 导航档：单粘贴块 + collect/ingest ----------
def make_nonce():
    return secrets.token_hex(8)


def _begin(nonce, idx):
    return f"<<<OPSAXIOM:{nonce}:BEGIN:{idx}>>>"


def _end(nonce, idx):
    return f"<<<OPSAXIOM:{nonce}:END:{idx}>>>"


def render_paste_block(plan, nonce, only_manual=True):
    """把探针渲染成一个粘贴块：命令清单 + 供 ingest 切段的 nonce 边界。

    only_manual=True（导航档默认）：只列非自动探针（自动的已本机执行）；
    False：全部（纯导航档零凭据场景，人跑全部命令）。
    """
    probes = [p for p in flatten(plan)
              if not (only_manual and p["auto"])]
    lines = ["# 请把下面整块在目标上执行，输出连同边界标记一并贴回（END 结束）：",
             f"# 会话校验码 {nonce}（伪造的边界标记会被当作数据忽略）"]
    for p in probes:
        lines.append(_begin(nonce, p["index"]))
        lines.append(f"$ {p['cmd']}")
        lines.append(_end(nonce, p["index"]))
    return "\n".join(lines), probes


def build_collect_script(plan, nonce, only_manual=True):
    """自包含取证脚本：在目标上运行，产出 nonce 分隔的输出，供 ingest 回灌。"""
    probes = [p for p in flatten(plan)
              if not (only_manual and p["auto"])]
    out = ["#!/bin/sh",
           "# OpsAxiom 取证脚本（自包含，均为已验证 Skill 的只读命令）。",
           f"NONCE={nonce}"]
    for p in probes:
        cmd = p["cmd"].replace("'", "'\\''")
        out.append(f"echo \"<<<OPSAXIOM:$NONCE:BEGIN:{p['index']}>>>\"")
        out.append(f"eval '{cmd}' 2>&1")
        out.append(f"echo \"<<<OPSAXIOM:$NONCE:END:{p['index']}>>>\"")
    return "\n".join(out) + "\n"


def ingest(text, plan, nonce, store, params=None, now=None):
    """回灌：按【带本会话 nonce 的】边界切段，映射到探针，解析入库。

    对抗①：只有精确匹配 nonce 的边界才是切点；伪造/无 nonce 的标记留在段内当数据。
    返回：{ingested:[node...], ignored_forged:int}。
    """
    probes = {p["index"]: p for p in flatten(plan)}
    begin = re.compile(r"^<<<OPSAXIOM:" + re.escape(nonce) + r":BEGIN:(\d+)>>>$")
    end = re.compile(r"^<<<OPSAXIOM:" + re.escape(nonce) + r":END:(\d+)>>>$")
    lines = text.splitlines()
    ingested, forged = [], 0
    # 统计伪造边界：形似 OPSAXIOM 边界但 nonce 不符（诚实计数，便于告警）
    forged_pat = re.compile(r"^<<<OPSAXIOM:.*:(?:BEGIN|END):\d+>>>$")
    i, cur_idx, buf = 0, None, []
    while i < len(lines):
        ln = lines[i]
        mb = begin.match(ln)
        me = end.match(ln)
        if cur_idx is None and mb:
            cur_idx = int(mb.group(1)); buf = []
        elif cur_idx is not None and me and int(me.group(1)) == cur_idx:
            p = probes.get(cur_idx)
            if p is not None:
                _store_result(store, p, "\n".join(buf), now)
                ingested.append(p["node"])
            cur_idx, buf = None, []
        else:
            if forged_pat.match(ln) and not (mb or me):
                forged += 1                          # 伪造边界：计数后并入数据
            if cur_idx is not None:
                buf.append(ln)
        i += 1
    return {"ingested": ingested, "ignored_forged": forged}


# ---------- 本机自动执行的一次性授权（trust.yaml）----------
def _trust_file():
    base = pathlib.Path(__import__("os").environ.get(
        "OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))
    return base / "trust.yaml"


def is_trusted(target=LOCAL, path=None):
    f = pathlib.Path(path) if path else _trust_file()
    if not f.exists():
        return False
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return target in (data.get("auto_exec") or [])


def grant_trust(target=LOCAL, path=None):
    """记录"允许对该目标本机自动执行只读取证"。逐目标累积，非全局开关（R3）。"""
    f = pathlib.Path(path) if path else _trust_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    data = data or {}
    lst = data.setdefault("auto_exec", [])
    if target not in lst:
        lst.append(target)
    f.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return f
