"""
overlay.py —— 个人叠加层加载器（docs/13 §2，I-9）。

overlay 贴在通用 Skill 上，只做三件事：填 source:local 参数、给节点贴注记
（links/caution）、预设 ask 答案。**绝不碰树**——出现 run/branch/when/otherwise/
tree/metadata/节点增删 即拒绝加载（否则 🔵 徽章验证的那棵树就被悄悄改了，
徽章不再诚实）。想改流程 → 那是 fork（I-10），不是 overlay。

红线（load 时强制）：
  - 顶层键只允许 {overlay, base, base_version, params, notes, answers}；
  - notes.<node> 只允许 {links, caution}；
  - 任何位置出现 run/branch/when/otherwise/tree/metadata/nodes/entry → 拒绝；
  - params 的值必须 shell-safe（T-3：含元字符即拒，防经 local 参数注入）。

个人层，永不出门（--share 导出由 I-11 剥离；打包/CI 不收 overlay 目录）。
"""
import os
import pathlib
import re

import yaml

_ALLOWED_TOP = {"overlay", "base", "base_version", "params", "notes", "answers"}
_ALLOWED_NOTE = {"links", "caution"}
# 出现即视为"试图改树/改元数据"的禁用键（递归全文检查）
_FORBIDDEN = {"run", "branch", "when", "otherwise", "tree", "nodes", "entry",
              "metadata", "type", "goto"}
_META_VAL = re.compile(r"[;&|`$<>(){}\n]")     # 与 sweep T-3 同源


class OverlayError(Exception):
    pass


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


def overlay_path(skill_id):
    return _home() / "overlays" / f"{skill_id}.yaml"


def _scan_forbidden(obj, trail=""):
    """递归查禁用键——不管藏多深，试图改树/元数据都拒。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _FORBIDDEN:
                raise OverlayError(
                    f"overlay 不得包含 '{k}'（在 {trail or '顶层'}）——overlay 只能填参数/"
                    f"贴注记/预设答案，改树请用 fork（opsaxiom skill fork）")
            _scan_forbidden(v, f"{trail}.{k}" if trail else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_forbidden(v, f"{trail}[{i}]")


def validate(ov):
    """结构 + 红线校验。任何违规 → OverlayError（整文件拒绝，不部分放行）。"""
    if not isinstance(ov, dict):
        raise OverlayError("overlay 必须是映射")
    bad_top = set(ov) - _ALLOWED_TOP
    if bad_top:
        raise OverlayError(f"overlay 顶层只允许 {sorted(_ALLOWED_TOP)}，出现非法键 {sorted(bad_top)}")
    if "base" not in ov:
        raise OverlayError("overlay 必须声明 base（叠加在哪个 Skill 上）")
    _scan_forbidden(ov)                                  # 递归禁用键（含 notes 里藏 run 等）
    # notes 每个节点只允许 links/caution
    for node, note in (ov.get("notes") or {}).items():
        if not isinstance(note, dict):
            raise OverlayError(f"notes.{node} 必须是映射")
        bad = set(note) - _ALLOWED_NOTE
        if bad:
            raise OverlayError(f"notes.{node} 只允许 {sorted(_ALLOWED_NOTE)}，出现 {sorted(bad)}")
    # params 值必须 shell-safe（T-3：防经 local 参数注入命令）
    for k, v in (ov.get("params") or {}).items():
        if _META_VAL.search(str(v)):
            raise OverlayError(f"params.{k} 的值含 shell 元字符，拒绝加载（防注入，T-3）：{v!r}")
    return ov


def load(skill_id, path=None):
    """加载并校验 overlay；不存在返回 None。"""
    f = pathlib.Path(path) if path else overlay_path(skill_id)
    if not f.exists():
        return None
    ov = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return validate(ov)


# ---------- 合并辅助（供 incident/repl；纯函数，不改 skill 本体）----------

def local_params(ov):
    return dict((ov or {}).get("params") or {})


def note_for(ov, node_id):
    """某节点的 overlay 注记 {links, caution}，无则 None。"""
    return ((ov or {}).get("notes") or {}).get(node_id)


def answer_for(ov, ask_id):
    return ((ov or {}).get("answers") or {}).get(ask_id)


def unmatched_nodes(ov, skill):
    """overlay 的 notes/answers 引用了但 Skill 里不存在的节点 id（供 skill doctor 黄牌，
    不阻塞排查——失配跳过即可）。"""
    ids = {n["id"] for n in skill.get("tree", {}).get("nodes", [])}
    refs = set((ov or {}).get("notes") or {}) | set((ov or {}).get("answers") or {})
    return sorted(refs - ids)


def render_note(note):
    """把一条 note 渲染成带 📌 前缀的展示行（个人内容一眼可辨）。"""
    if not note:
        return ""
    parts = []
    if note.get("caution"):
        parts.append(f"📌 {note['caution']}")
    for l in (note.get("links") or []):
        if l.get("url"):
            parts.append(f"📌 {l.get('name', l['url'])}（{l['url']}）")
    return "\n".join(parts)
