"""
出站文本脱敏（R11 单一事实来源）。

凡是要离开本机进外部服务的文本——IM 卡片（webhook）、送 LLM 的上下文（Z-5）——
都先过这里。凭据永不入外部上下文。此前 opsaxiom-webhook 内联了这套正则（F-17），
现收敛到一处，避免各出站点各写一份（T-1 标识符/规则单一事实来源）。
"""
import re

_SECRET_PATS = [
    re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|bearer)\b\s*[:=]?\s*\S+"),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),          # user:pass@host
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{6,}|xox[baprs]-[A-Za-z0-9-]{6,}|AKIA[0-9A-Z]{8,})\b"),  # 常见 token
]

MASK = "〔已脱敏〕"


def redact(text):
    """把常见凭据形态替换为脱敏占位。text 可为 None。"""
    for p in _SECRET_PATS:
        text = p.sub(MASK, text or "")
    return text
