"""
LLM 适配层（Z-5，docs/09 §3）——可选、可降级，只做三件事。

这是 docs/01 §1"编译时智能 vs 运行时选择"的最终兑现：**模型是外壳，引擎是法律。**
LLM 只做理解/叙事/建议，绝不碰命令与判读。三个调用点每一处都有无模型降级路径，
**无 model.yaml 时全功能可用**（导航档零依赖承诺不变，R3）。

铁律（对应宪法条款，全部由本模块的代码结构强制，不靠提示词自觉）：
- LLM 永不生成命令——本模块不设"出命令"的调用点；命令只来自已验证 Skill（R10）。
- LLM 永不判分支——判读只由 exprlang + 解析器完成（R9）；本模块不求值任何分支。
- LLM 输出全部过 schema/白名单，不符即静默丢弃走降级（R10）。
- 送 LLM 的上下文先过 redact 脱敏（R11）。
- LLM 抽取的 param 值再过 shell 安全校验（不安全即丢），因为它会流进命令（T-3）。

后端：ollama 与 openai-compatible 两种，均走 stdlib urllib（不加依赖）。
可测：所有调用点接受注入的 caller(prompt, system)->str|None，测试喂假响应（含攻击载荷）。
"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from redact import redact          # noqa: E402
from sweep import is_shell_safe    # noqa: E402  param 值安全校验复用


def config_path():
    base = pathlib.Path(os.environ.get(
        "OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))
    return base / "model.yaml"


def load_config(path=None):
    """读 model.yaml；缺文件/未启用/解析失败 → None（= 无模型，全走降级）。"""
    import yaml
    p = pathlib.Path(path) if path else config_path()
    if not p.exists():
        return None
    try:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return cfg if cfg.get("enabled") else None


# ---------- 后端调用（stdlib urllib）----------
def _http_json(url, payload, timeout=20):
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def backend_call(cfg, prompt, system):
    """按 cfg.backend 调后端，返回文本；任何异常/超时 → None（触发降级）。"""
    try:
        backend = cfg.get("backend")
        model = cfg.get("model", "")
        if backend == "ollama":
            url = cfg.get("endpoint", "http://localhost:11434") + "/api/chat"
            data = _http_json(url, {
                "model": model, "stream": False,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}]})
            return (data.get("message") or {}).get("content")
        if backend in ("openai", "openai-compatible"):
            url = cfg.get("endpoint", "").rstrip("/") + "/chat/completions"
            headers_key = cfg.get("api_key")
            payload = {"model": model,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": prompt}]}
            import urllib.request
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         **({"Authorization": f"Bearer {headers_key}"} if headers_key else {})})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except Exception:
        return None
    return None


def _caller(cfg, caller):
    """解析实际调用器：优先注入的 caller（测试），否则真实后端。"""
    if caller is not None:
        return caller
    if cfg is None:
        return None
    return lambda prompt, system: backend_call(cfg, prompt, system)


def _extract_json(text):
    """从模型输出里抠第一个 JSON 对象；失败 → None。"""
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


# ---------- 调用点 1：intake 理解 ----------
_INTAKE_SYS = (
    "你是运维分诊助手。把用户的故障陈述转成 JSON：{\"params\":{键:值},\"entities\":[...]}"
    "。params 只填你确信的实体（如 mount=/data, peer_ip=10.0.0.1, xid=79）。"
    "只输出 JSON，不要命令、不要解释。")


def intake(symptom, config=None, caller=None):
    """NL → 结构化 params（供渲染命令）。返回 {"params":{...}, "entities":[...]}。

    降级（无模型/超时/输出不合法/无 JSON）→ {"params":{}, "entities":[]}，
    调用方照常用 bigram diagnose。抽出的 param 值过 shell 安全校验（不安全即丢，T-3）。
    """
    fallback = {"params": {}, "entities": [], "degraded": True}
    call = _caller(config, caller)
    if call is None:
        return fallback
    raw = call(redact(symptom), _INTAKE_SYS)     # R11：送模型前脱敏
    obj = _extract_json(raw)
    if not isinstance(obj, dict):
        return fallback
    params = {}
    for k, v in (obj.get("params") or {}).items():
        if not (isinstance(k, str) and k.isidentifier()):
            continue                              # 键须是合法标识符（能进模板）
        v = str(v)
        if is_shell_safe(v):                      # T-3：不安全的 param 值一律丢
            params[k] = v
    ents = [str(x) for x in (obj.get("entities") or [])][:12]
    return {"params": params, "entities": ents, "degraded": False}


# ---------- 调用点 2：叙事 ----------
_NARRATE_SYS = (
    "你是运维助手。把给定的结构化判读用一句中文人话讲清楚，"
    "只解释、不建议命令、不超过 40 字。只输出这句话。")


def narrate(conclusion, evidence=None, config=None, caller=None):
    """结构化结论 → 一句人话。降级 → 原样返回 conclusion（模板渲染结果）。

    叙事是纯展示：返回值只用于打印，绝不进任何执行/判读路径（注入无从生效）。
    """
    call = _caller(config, caller)
    if call is None:
        return conclusion
    ev = "; ".join(f"{e.get('field')}={e.get('value')}" for e in (evidence or [])[:6])
    prompt = redact(f"结论：{conclusion}\n证据：{ev}")
    out = call(prompt, _NARRATE_SYS)
    if not out or not out.strip():
        return conclusion
    return redact(out.strip()[:120])              # 出站再脱敏一次，且截断


# ---------- 调用点 3：escalate 助理 ----------
_SUGGEST_SYS = (
    "你是运维分诊助手。给定故障摘要与【可选 Skill id 白名单】，"
    "只从白名单里挑最相关的一个 id 输出 JSON：{\"skill_id\":\"<白名单里的 id>\"}。"
    "白名单外的一律不许输出。只输出 JSON。")


def suggest_skill(handover, idx, config=None, caller=None):
    """移交时建议下一个库内 Skill id。返回 id（∈ idx）或 None。

    白名单强制：模型给的 id 不在库内 → 丢弃（返回 None）。这挡住"模型越权
    推荐不存在/编造的 Skill"。徽章由调用方从 idx 查，模型无权抬升可信度（R8）。
    """
    call = _caller(config, caller)
    if call is None:
        return None
    ids = {s["id"] for s in idx}
    listing = ", ".join(sorted(ids))
    prompt = redact(f"故障：{handover.get('symptom','')}\n"
                    f"已排除：{handover.get('refuted', [])}\n"
                    f"白名单 id：{listing}")
    obj = _extract_json(call(prompt, _SUGGEST_SYS))
    if not isinstance(obj, dict):
        return None
    sid = obj.get("skill_id")
    return sid if sid in ids else None            # 越权/编造 id → None
