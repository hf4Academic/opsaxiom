"""
解析器库（O-5 起，Q-2 增字段声明）——确定性工具层的一部分（黄金准则 R9）。

模型不裸眼读原始命令输出：解析器把 CLI/系统命令输出转成结构化数据，
供决策树的受限表达式（rows[].field 等）求值。

注册表：名字 -> (解析函数(text)->dict|list, 字段声明)
字段声明 = {"rows": [行字段...], "scalars": [顶层标量字段...], "lines": bool}
供校验器（Q-2）检查 when/assert 引用的字段是否真由该解析器产出。
命名约定：<家族>/<名字>-v<版本>，如 table/df-v1、ntc/cisco_ios/bgp-summary。
"""
_REGISTRY = {}
_FIELDS = {}


def register(name, fn, fields=None):
    _REGISTRY[name] = fn
    if fields is not None:
        _FIELDS[name] = fields


def get_parser(name):
    """返回解析函数；未注册返回 None。ntc/* 形式转交 ntc 包装器。"""
    if name in _REGISTRY:
        return _REGISTRY[name]
    if name.startswith("ntc/"):
        from . import ntc
        return ntc.make_parser(name)
    return None


_YAML_FIELDS = None


def get_fields(name):
    """返回该解析器的字段声明；代码注册优先，否则回退 parser_fields.yaml；均无返回 None。"""
    if name in _FIELDS:
        return _FIELDS[name]
    global _YAML_FIELDS
    if _YAML_FIELDS is None:
        import pathlib
        import yaml
        p = pathlib.Path(__file__).resolve().parent.parent / "parser_fields.yaml"
        try:
            _YAML_FIELDS = yaml.safe_load(p.read_text(encoding="utf-8")).get("parsers", {})
        except Exception:
            _YAML_FIELDS = {}
    return _YAML_FIELDS.get(name)


def registered_names():
    return sorted(_REGISTRY)


# 填充注册表（各子模块提供 install(register)）
from . import table   # noqa: E402
from . import health  # noqa: E402
from . import mw      # noqa: E402
table.install(register)
health.install(register)
mw.install(register)
