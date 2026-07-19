"""
network_conn.py —— 网络设备连接器（docs/12 §4，I-5）：cisco_ios / huawei_vrp / junos。

只负责"拨通并发一条只读 show/display 命令"，不做安全判断——白名单/授权/审计全在
gate.py。这里只提供平台提示符适配与行协议交互。

硬化：禁 enable/system-view/configure 等提权与配置模式（见 gate 白名单，此处再用
平台配置提示符兜底——若响应出现在配置模式提示符下立即断开并拒绝）；超时 10s。
"""
import re

import paramiko

# 配置/提权模式提示符（出现在响应尾部即视为进入了非只读上下文，立即拒）
_CONFIG_PROMPT = re.compile(
    r"(config[\w-]*\)|system-view\]|edit\]|\{edit\}|# *config)", re.IGNORECASE)


class NetworkError(Exception):
    pass


# 各平台的行尾提示符特征（用于判定命令已返回、抓取完整输出）
_PROMPT_TAIL = {
    "cisco_ios": re.compile(r"[>\#]\s*$"),
    "huawei_vrp": re.compile(r"[\]>]\s*$"),
    "junos": re.compile(r"[>%]\s*$"),
}


def exec_readonly(target, cred, cmd, timeout=10):
    """在网络设备上执行一条只读命令，返回 (0, stdout, stderr)。

    认证：网络设备多为密码（keyring 凭证，I-6 接线）或密钥（file/agent）。
    这里只接受 keyring 解析出的 username/password 或密钥——与 access 契约一致。
    """
    import access
    platform = target.get("platform", "cisco_ios")
    host = target.get("host")
    user = target.get("user")
    port = int(target.get("port", 22))
    if not host:
        raise NetworkError("网络设备缺 host")

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.WarningPolicy())   # 设备证书多自签，先放行告警
    cli.load_system_host_keys()
    kw = dict(hostname=host, port=port, username=user, timeout=timeout,
              banner_timeout=timeout, auth_timeout=timeout, look_for_keys=False,
              allow_agent=False)
    if cred.kind == "file":
        kw["key_filename"] = cred.get("path")
    elif cred.kind == "keyring":
        kw["username"] = user or cred.get("username")
        kw["password"] = cred.get("password")   # 来自本机钥匙串（I-6），仅内存
    elif cred.kind == "agent":
        kw["look_for_keys"] = True
        kw["allow_agent"] = True
    try:
        cli.connect(**kw)
        chan = cli.invoke_shell()                 # 行协议需要 shell channel
        chan.settimeout(timeout)
        _drain(chan, platform)                    # 吃掉登录横幅/首个提示符
        chan.send(cmd + "\n")
        out = _read_until_prompt(chan, platform, timeout)
        if _CONFIG_PROMPT.search(out[-200:]):
            raise NetworkError("检测到配置/提权模式提示符——只读通道拒绝进入（安全兜底）")
        return 0, out, ""
    except paramiko.SSHException as e:
        raise NetworkError(f"网络设备连接/执行失败：{e}") from e
    finally:
        cli.close()


def _drain(chan, platform, brief=1.0):
    import time
    time.sleep(brief)
    buf = b""
    while chan.recv_ready():
        buf += chan.recv(65535)
    return buf.decode("utf-8", "replace")


def _read_until_prompt(chan, platform, timeout):
    import time
    tail_re = _PROMPT_TAIL.get(platform, re.compile(r"[>\]#]\s*$"))
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            buf += chan.recv(65535)
            text = buf.decode("utf-8", "replace")
            if tail_re.search(text.rstrip().splitlines()[-1] if text.strip() else ""):
                return text
        else:
            time.sleep(0.1)
    return buf.decode("utf-8", "replace")
