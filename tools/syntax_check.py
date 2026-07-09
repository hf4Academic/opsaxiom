"""
S6 命令语法树校验（O-5：从占位升为真实校验）。

策略（与 O-2 约定一致）：
  - 网络平台（cisco_ios / huawei_vrp / junos，tools/syntax/*.yaml 中 kind: network）：
    命令归一后必须匹配某合法前缀，否则判 ERROR —— 拦截跨平台混用与不存在命令（CLI 幻觉，R10）。
  - 其他平台（linux / kubectl 等，无语法树）：跳过（返回 []），host 侧语法校验为后续工作。

前缀匹配是"尽力"而非精确文法：只保证动词/子命令链合法，不校验参数取值。
这对最高危的 CLI 幻觉（把 A 厂命令用到 B 厂设备）已足够有效。
"""
import pathlib
import re

import yaml

_SYNTAX_DIR = pathlib.Path(__file__).resolve().parent / "syntax"

_TEMPLATE = re.compile(r"\{\{[^}]*\}\}")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def _load_trees():
    trees = {}
    if not _SYNTAX_DIR.is_dir():
        return trees
    for f in _SYNTAX_DIR.glob("*.yaml"):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        plat = data.get("platform")
        prefixes = [tuple(p.split()) for p in data.get("prefixes", [])]
        trees[plat] = {"kind": data.get("kind", "network"), "prefixes": prefixes}
    return trees


_TREES = _load_trees()


def covered_platforms():
    return set(_TREES)


def _normalize(command):
    """截到首个 | ; 换行前，去模板与引号，返回 token 列表。"""
    head = re.split(r"[|;\n]", command, maxsplit=1)[0]
    head = _QUOTED.sub("", _TEMPLATE.sub("", head))
    return head.split()


def check_command(platform, command):
    """返回问题列表，元素为 (level, message)。level ∈ {'ERROR'}。"""
    tree = _TREES.get(platform)
    if not tree:
        return []  # 无语法树的平台：跳过
    tokens = _normalize(command)
    if not tokens:
        return []
    for pref in tree["prefixes"]:
        if tuple(tokens[:len(pref)]) == pref:
            return []
    if tree["kind"] == "network":
        return [("ERROR",
                 f"命令未匹配任何已知 {platform} 合法前缀（疑似 CLI 幻觉或跨平台混用）：{command!r}")]
    return [("ERROR", f"命令未匹配 {platform} 语法树：{command!r}")]
