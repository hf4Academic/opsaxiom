"""
S6 命令语法树校验 —— O-2 阶段的接口占位。

本轮返回 INFO 级提示（不阻断），真实的平台命令前缀树在 O-5 实现（tools/syntax/）。
届时 check_command 将改为对 network 域强制 ERROR、host 域尽力 WARNING。

对外接口：check_command(platform:str, command:str) -> list[Issue-like dict]
"""

_DEFERRED = True  # O-5 置为 False


def check_command(platform, command):
    """当前占位：不产生逐命令噪声。返回空列表。
    validate.py 会在每个 skill 末尾打印一条 INFO 说明 S6 已延后。"""
    return []


def is_deferred():
    return _DEFERRED
