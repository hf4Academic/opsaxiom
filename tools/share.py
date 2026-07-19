"""
share.py —— 对外分享时的个人层剥离（docs/13 §4，I-11）。

导出故障报告/卷宗用于分享（贴工单、发社区）时，剥离全部个人内容：
  - 📌 标记的 overlay 注记行与 linkbook"你的相关页面"行；
  - 兜底：经 redact 处理内网 URL / 敏感串（redact.py 单一来源）。

个人层（overlay/linkbook/skills-local）本就不该出门——这里做的是"导出物"的
最后一道剥离，与打包器/CI 的出门拦截互补。
"""
import re

import redact

_PIN_LINE = re.compile(r"^\s*📌.*$", re.MULTILINE)
# 内网/私网 URL：私网段 IP 或常见内网域（.corp/.internal/.lan/.local）——
# linkbook/overlay 里用户贴的多是这类，分享时剥掉域名部分留协议占位。
_PRIVATE_URL = re.compile(
    r"https?://(?:"
    r"10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+"
    r"|[\w.-]+\.(?:corp|internal|lan|local|intra|home)"
    r")(?::\d+)?(?:/[^\s)]*)?", re.IGNORECASE)


def strip_personal(text):
    """剥离 📌 行（overlay 注记 / linkbook 行）+ 内网 URL 域名 + redact 凭据兜底。"""
    text = _PIN_LINE.sub("", text)
    text = _PRIVATE_URL.sub("〔内网地址〕", text)
    text = re.sub(r"\n{3,}", "\n\n", text)          # 清理剥离后的连续空行
    try:
        return redact.redact(text)
    except Exception:
        return text
