"""
http_conn.py —— HTTP 管理接口连接器（docs/12 §4，I-5）：ES/Prometheus/RabbitMQ 等。

只负责"发一个 GET 并返回响应体"，不做安全判断——方法/路径白名单全在 gate.py
（只放行 GET、且路径必须在 Skill 声明的前缀内）。这里只处理 transport：
base 拼接、超时、可选 TLS 验证开关（verify:false 显式声明才放行，见 gate）。
"""
import urllib.error
import urllib.request


class HTTPError(Exception):
    pass


def get_readonly(target, cred, path, timeout=10):
    """GET 一个只读端点，返回 (status, body, err)。仅 GET；路径由 gate 已校验。"""
    base = target.get("base", "").rstrip("/")
    if not base:
        raise HTTPError("http 目标缺 base")
    if not path.startswith("/"):
        path = "/" + path
    url = base + path
    ctx = _ssl_ctx(target)
    req = urllib.request.Request(url, method="GET")
    # 认证：keyring 解析出的 token → Authorization header（仅内存，不落盘）
    if cred.kind == "keyring" and cred.get("token"):
        req.add_header("Authorization", f"Bearer {cred.get('token')}")
    elif cred.kind == "keyring" and cred.get("username"):
        import base64
        raw = f"{cred.get('username')}:{cred.get('password','')}".encode()
        req.add_header("Authorization", "Basic " + base64.b64encode(raw).decode())
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        raise HTTPError(f"HTTP 请求失败：{e}") from e


def _ssl_ctx(target):
    """TLS：默认系统 CA 验证；target 显式 verify:false 才放行自签（gate 会黄牌）。"""
    import ssl
    if target.get("verify", True) is False:
        return ssl._create_unverified_context()
    return ssl.create_default_context()
