"""
cred.py —— P1 本机凭证存取（docs/12 §3，I-6）：`opsaxiom cred set/rm/list`。

为网络设备密码、HTTP token 这类"没有密钥体系"的凭证提供本地安全存储。
优先 OS keyring（SecretService/macOS Keychain/Windows Vault，经由 keyring 库）；
keyring 不可用时降级为 cryptography.fernet + 主口令加密的本地文件（0600）。

红线：值只进钥匙串/加密文件与内存——`cred list` 只显示条目名与字段名，
绝不回显值；读取只在 resolve 凭证时短暂入内存（R-A2）。

存储布局：
  密钥材料 → OS keyring(service=opsaxiom, key=<name>) 或降级文件；
  元数据（username 等非敏感字段）→ ~/.opsaxiom/creds/<name>.json（0600）。
"""
import base64
import getpass
import hashlib
import json
import os
import pathlib
import sys

SERVICE = "opsaxiom"


class CredError(Exception):
    pass


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


def _creds_dir():
    return _home() / "creds"


# ---------- 后端选择：OS keyring 优先，fernet 文件降级 ----------

def _os_keyring():
    """可用的 OS keyring 后端；不可用（无桌面/headless）返回 None。"""
    try:
        import keyring
        kr = keyring.get_keyring()
        # 探测性读写，确认不是 fail 后端
        probe = "opsaxiom.__probe__"
        kr.set_password(SERVICE, probe, "1")
        kr.delete_password(SERVICE, probe)
        return kr
    except Exception:
        return None


def _fernet_key(master):
    """主口令 → 32 字节 fernet 密钥（PBKDF2 简化：SHA256 直接派生，salt 固定在本机）。
    主口令不进任何文件——这是降级路径的兜底，安全性弱于 OS keyring 但可用。"""
    salt = _home().name.encode() + b".opsaxiom"
    return base64.urlsafe_b64encode(hashlib.pbkdf2_hmac(
        "sha256", master.encode(), salt, 100_000, dklen=32))


def _secret_file(name):
    return _creds_dir() / f"{name}.secret"


# ---------- 读写 ----------

def set_cred(name, fields, master=None):
    """写入一条凭证。fields 中含敏感键（password/token/secret/api_key）→ 入钥匙串，
    其余（username 等）→ 元数据 json。返回后端名（os-keyring / fernet-file）。"""
    _creds_dir().mkdir(parents=True, exist_ok=True)
    fields = dict(fields)
    secret = {}
    for k in ("password", "token", "secret", "api_key"):
        if fields.get(k):
            secret[k] = fields.pop(k)
    backend = "os-keyring"
    kr = _os_keyring()
    if kr and secret:
        blob = json.dumps(secret)
        kr.set_password(SERVICE, name, blob)
    elif secret:
        backend = "fernet-file"
        if master is None:
            if not sys.stdin.isatty():
                raise CredError(f"无 OS keyring，降级为加密文件需主口令（传 master 或在终端运行）")
            master = getpass.getpass("降级为本地加密文件，请设主口令：")
        from cryptography.fernet import Fernet
        blob = Fernet(_fernet_key(master)).encrypt(json.dumps(secret).encode())
        _secret_file(name).write_bytes(blob)
        os.chmod(_secret_file(name), 0o600)
    meta = {k: v for k, v in fields.items() if v is not None}
    mf = _creds_dir() / f"{name}.json"
    mf.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.chmod(mf, 0o600)
    return backend


def get_cred(name, master=None):
    """读取一条凭证为 {username?, password?/token?, ...}。

    返回 None：凭证【不存在】（无任何存储痕迹）。
    抛 CredError：凭证存在但无法解锁（主口令错误/缺主口令/后端坏）——
    与"不存在"严格区分，调用方据此提示补口令而非提示"先 cred set"。
    """
    mf = _creds_dir() / f"{name}.json"
    sf = _secret_file(name)
    kr = _os_keyring()
    os_secret = kr.get_password(SERVICE, name) if kr else None
    has_any = mf.exists() or sf.exists() or os_secret is not None
    if not has_any:
        return None
    out = {}
    if mf.exists():
        out.update(json.loads(mf.read_text(encoding="utf-8")))
    if kr and os_secret:
        out.update(json.loads(os_secret))
        return out
    sf = _secret_file(name)
    if sf.exists():
        if master is None:
            # 降级文件必须主口令；非交互/未提供时给可行动的错误，不盲等 getpass
            if not sys.stdin.isatty():
                raise CredError(f"凭证 {name} 是加密文件，需主口令解锁（传 master 或在终端里运行）")
            master = getpass.getpass(f"解锁凭证 {name} 的主口令：")
        from cryptography.fernet import Fernet
        try:
            blob = Fernet(_fernet_key(master)).decrypt(sf.read_bytes())
        except CredError:
            raise
        except Exception:
            raise CredError("主口令错误，无法解锁凭证")
        out.update(json.loads(blob.decode()))
    return out or None


def rm_cred(name):
    """删除一条凭证（各后端都清）。返回是否删到了东西。"""
    removed = False
    kr = _os_keyring()
    if kr:
        try:
            kr.delete_password(SERVICE, name); removed = True
        except Exception:
            pass
    for f in (_creds_dir() / f"{name}.json", _secret_file(name)):
        if f.exists():
            f.unlink(); removed = True
    return removed


def list_creds():
    """列出条目名与字段名（绝不显示值）。"""
    out = []
    d = _creds_dir()
    if d.is_dir():
        for mf in sorted(d.glob("*.json")):
            meta = json.loads(mf.read_text(encoding="utf-8"))
            fields = sorted(meta.keys())
            # 敏感键是否已存（只显示有无，不显示值）
            if _secret_file(mf.stem).exists() or _has_os_secret(mf.stem):
                fields.append("password/token")
            out.append({"name": mf.stem, "fields": fields})
    return out


def _has_os_secret(name):
    kr = _os_keyring()
    if not kr:
        return False
    try:
        return kr.get_password(SERVICE, name) is not None
    except Exception:
        return False
