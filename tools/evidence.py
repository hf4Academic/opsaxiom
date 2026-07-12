"""
检查前沿提取与取证计划（Z-2，docs/09 §1.2）。

把"逐节点问答"改造成"一轮批量取证"的静态分析层：对每个候选假设 Skill，
提取【从 entry 可达、命令模板参数当前已知】的 check/discovery 节点，多假设合并去重，
按波次分组，产出一个取证计划。运行时（Z-3/Z-4）据此一次性采集、再让树在事实上干跑。

两个关键区分（都来自实测三种树形态：disk-full/bgp/xid-error）：
- **纳入前沿** 只看"可达 + 命令可渲染"——网络设备 `show` 命令虽不在 linux 只读白名单，
  仍要纳入（人在设备上跑，走粘贴块）。
- **是否自动执行**（auto）另判：仅当 target 是本机且命令过 `_is_readonly` 白名单时才自动跑；
  否则渲染进粘贴块由人执行。这样 F-16 的只读白名单纪律一分不松，网络设备也不被误判。

波次：一波取证的解析输出（解析器声明的标量字段）并入"已知"集，据此解锁下一波
可渲染的节点。绝大多数树是单波（命令只引用 alert 参数）；引用派生值的进后波。
不可渲染的节点（依赖 ask 输入 / 未产出的派生量）留到干跑时按需补采——诚实，不硬凑。
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim"))
import parsers          # noqa: E402
import runtime          # noqa: E402  复用规范渲染器
from run_sim import _is_readonly  # noqa: E402  复用只读白名单（不新开口子）
from facts import LOCAL, normalize_cmd  # noqa: E402

_VARRE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _cmd_of(run):
    """取 run dict 的（连接器, 命令）——任一平台键，与 runtime._cmd_for 同语义。"""
    if isinstance(run, dict) and run:
        for conn, c in run.items():
            return conn, c
    return None, None


def _base_vars(text):
    """命令模板里 {{expr}} 引用的基名集合（取表达式前导标识符）。
    命令只引用参数（{{mount}}/{{peer_ip}}/{{sid}}…），故基名即参数名。"""
    out = set()
    for m in _VARRE.finditer(text or ""):
        mm = re.match(r"[A-Za-z_]\w*", m.group(1).strip())
        if mm:
            out.add(mm.group(0))
    return out


def reachable_checks(skill):
    """从 entry 广度遍历所有出边（branch/otherwise/options/goto），
    按首次到达顺序收集 check 节点。稳定顺序便于测试与展示。"""
    nodes = {n["id"]: n for n in skill["tree"]["nodes"]}
    seen, order, q = set(), [], [skill["tree"]["entry"]]
    while q:
        nid = q.pop(0)
        n = nodes.get(nid)
        if not n or nid in seen:
            continue
        seen.add(nid)
        if n["type"] == "check":
            order.append(n)
        for br in n.get("branch", []) or []:
            q.append(br.get("goto"))
        if n.get("otherwise"):
            q.append(n["otherwise"])
        for o in n.get("options", []) or []:
            q.append(o.get("goto"))
        if n.get("goto"):
            q.append(n["goto"])
    return order


def _candidates(skill):
    """前沿候选 = discovery 命令 + 可达 check 命令，各带 (node, conn, cmd, parser, kind)。"""
    out = []
    for d in skill.get("discovery", []) or []:
        conn, c = _cmd_of(d.get("run"))
        if c:
            out.append((d["id"], conn, c, d.get("parser"), "discovery"))
    for n in reachable_checks(skill):
        conn, c = _cmd_of(n.get("run"))
        if c:
            out.append((n["id"], conn, c, n.get("parser"), "check"))
    return out


def extract_frontier(skill, params, target=LOCAL):
    """单假设前沿：返回 probe 列表（含 wave/auto/rendered cmd）。

    probe = {skill_id, node, kind, connector, cmd_template, cmd(已渲染),
             parser, wave, auto, target}
    """
    skill_id = skill["metadata"]["id"]
    ctx = dict(params)
    ctx.setdefault("sid", "sess")
    known = set(ctx)                       # 已知参数名（含 sid）
    cands = _candidates(skill)
    probes, scheduled, wave = [], set(), 1
    while True:
        ready = [x for x in cands
                 if x[0] not in scheduled and _base_vars(x[2]) <= known]
        if not ready:
            break
        for nid, conn, c, parser, kind in ready:
            rc = runtime.render(c, ctx)
            auto = (target == LOCAL) and _is_readonly(rc)
            probes.append({
                "skill_id": skill_id, "node": nid, "kind": kind,
                "connector": conn, "cmd_template": c, "cmd": rc,
                "parser": parser, "wave": wave, "auto": auto, "target": target})
            scheduled.add(nid)
        # 本波解析输出并入已知，可能解锁下一波
        for nid, conn, c, parser, kind in ready:
            fields = parsers.get_fields(parser) if parser else None
            if fields:
                known |= set(fields.get("scalars", []) or [])
        wave += 1
    return probes


def build_plan(hypotheses, target=LOCAL):
    """多假设取证计划：合并各假设前沿，按事实键(target+归一化命令)去重，波次分组。

    hypotheses: [(skill_dict, params_dict), ...]（通常是 diagnose top-K）。
    去重后一条命令只采一次，但记录它服务于哪些假设（for_skills）——
    这是"多假设并行取证"省回合的核心：一次 df 同时喂给 inode 与 deleted-open 两个假设。
    返回：{"target", "waves":[{"wave", "probes":[...]}], "auto_count", "manual_count"}。
    """
    merged = {}
    for skill, params in hypotheses:
        for p in extract_frontier(skill, params, target=target):
            key = (p["target"], normalize_cmd(p["cmd"]))
            if key in merged:
                m = merged[key]
                if p["skill_id"] not in m["for_skills"]:
                    m["for_skills"].append(p["skill_id"])
                m["wave"] = min(m["wave"], p["wave"])   # 最早可采的波次为准
            else:
                q = dict(p)
                q["for_skills"] = [p["skill_id"]]
                merged[key] = q
    probes = list(merged.values())
    waves = {}
    for p in probes:
        waves.setdefault(p["wave"], []).append(p)
    plan_waves = [{"wave": w, "probes": waves[w]} for w in sorted(waves)]
    return {"target": target, "waves": plan_waves,
            "auto_count": sum(1 for p in probes if p["auto"]),
            "manual_count": sum(1 for p in probes if not p["auto"])}


def plan_commands(plan):
    """扁平化：按波次顺序列出去重后的命令（供展示/测试断言）。"""
    return [p["cmd"] for w in plan["waves"] for p in w["probes"]]
