"""
解析器库（O-5）——确定性工具层的一部分（黄金准则 R9）。

模型不裸眼读原始命令输出：解析器把 CLI/系统命令输出转成结构化数据，
供决策树的受限表达式（rows[].field 等）求值。

注册表：名字 -> 解析函数(text:str) -> dict|list
命名约定：<家族>/<名字>-v<版本>，如 table/df-v1、ntc/cisco_ios/bgp-summary。

网络设备解析优先复用 ntc-templates（见 ntc.py），不重复造轮子；
自研解析器只补 ntc 未覆盖的系统命令与国产设备。
"""
_REGISTRY = {}


def register(name, fn):
    _REGISTRY[name] = fn


def get_parser(name):
    """返回解析函数；未注册返回 None。ntc/* 形式转交 ntc 包装器。"""
    if name in _REGISTRY:
        return _REGISTRY[name]
    if name.startswith("ntc/"):
        from . import ntc
        return ntc.make_parser(name)
    return None


def registered_names():
    return sorted(_REGISTRY)


# 填充注册表（各子模块提供 install(register)）
from . import table  # noqa: E402
table.install(register)
