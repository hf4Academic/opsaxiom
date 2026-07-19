"""
linkbook.py —— 个人排查网页台账（docs/13 §1，I-8）。

`~/.opsaxiom/linkbook.yaml` 按 taxonomy 前缀挂内部网页；排查时按命中的
taxonomy 聚合出"📌 你的相关页面"。纯展示层：不进决策树、不进命令、不出门
（--share 导出时由 I-11 剥离）。个人内容，永不推送到远端。

匹配规则（docs/13 §1）：
  - 段级前缀：linkbook 键 `middleware/mysql` 命中 taxonomy
    `middleware/mysql/slow-query-storm`；但 `middleware/my` 不命中（按 / 分段，
    不做字符级前缀，避免 mysql/mysqld 误伤）。
  - `"*"` 全局键：任何排查都显示。
  - 最长前缀优先：更具体的键排在前，其次一般键，最后全局键；跨多个 taxonomy
    聚合并按 url 去重。
"""
import os
import pathlib

import yaml


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


def linkbook_file():
    return _home() / "linkbook.yaml"


def load(path=None):
    f = pathlib.Path(path) if path else linkbook_file()
    if not f.exists():
        return {}
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return data.get("links", {}) or {}


def _segs(s):
    return [p for p in s.strip("/").split("/") if p]


def _is_prefix(key, tax):
    """key 的段序列是否为 tax 段序列的前缀（段级，非字符级）。"""
    ks, ts = _segs(key), _segs(tax)
    return len(ks) <= len(ts) and ts[:len(ks)] == ks


def links_for(taxonomies, book=None):
    """给一组 taxonomy，返回聚合去重后的 [{name,url}]（最长前缀优先，全局垫底）。"""
    book = load() if book is None else book
    if not book:
        return []
    if isinstance(taxonomies, str):
        taxonomies = [taxonomies]
    scored = []   # (specificity, order_key, entry)
    seen_keys = set()
    for key, entries in book.items():
        if key in seen_keys:
            continue
        if key == "*":
            spec = -1
        else:
            # 命中任一 taxonomy 才纳入；特异度=键的段数（越长越具体）
            if not any(_is_prefix(key, t) for t in taxonomies):
                continue
            spec = len(_segs(key))
        seen_keys.add(key)
        for e in (entries or []):
            if isinstance(e, dict) and e.get("url"):
                scored.append((spec, e))
    # 具体优先（spec 大在前），全局 -1 垫底；同组内保持声明顺序
    scored.sort(key=lambda x: -x[0])
    out, seen_urls = [], set()
    for _, e in scored:
        if e["url"] in seen_urls:
            continue
        seen_urls.add(e["url"])
        out.append({"name": e.get("name", e["url"]), "url": e["url"]})
    return out


def render_line(taxonomies, book=None):
    """一行展示：'📌 你的相关页面：名A · 名B'；无命中返回空串。"""
    ls = links_for(taxonomies, book=book)
    if not ls:
        return ""
    return "📌 你的相关页面：" + " · ".join(f"{l['name']}（{l['url']}）" for l in ls)
