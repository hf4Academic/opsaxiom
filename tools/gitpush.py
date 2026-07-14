"""
gitpush.py —— 纯 Python 的 SSH git 推送（无需系统 ssh 客户端）。

背景：部分环境（容器/受限主机）没有 ssh 二进制，git 走 SSH 协议就推不了。
本工具用 paramiko + dulwich 自带一个最小 SSH vendor，直接推 refspec。
密钥默认 ~/.ssh/id_ed25519（公钥需已加到 git 托管方账号）。

用法：
  python tools/gitpush.py <local_repo> <git@host:owner/repo.git> [refspec]
  refspec 缺省 refs/heads/main:refs/heads/main
依赖：pip install paramiko dulwich（install.sh --with-push 可选装）。
"""
import pathlib
import sys


def _vendor(key_path):
    import paramiko
    from dulwich import client
    key = paramiko.Ed25519Key.from_private_key_file(str(key_path))

    class _Chan:
        def __init__(self, cl, ch):
            self.cl, self.ch = cl, ch

        def read(self, n=4096):
            try:
                return self.ch.recv(n)
            except Exception:
                return b""

        def write(self, data):
            self.ch.sendall(data)
            return len(data)

        def can_read(self):
            return self.ch.recv_ready()

        def close(self):
            try:
                self.ch.close()
            finally:
                self.cl.close()

    class _Vendor(client.SSHVendor):
        def run_command(self, host, command, username=None, port=None, **kw):
            cl = paramiko.SSHClient()
            cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            cl.connect(host, port=port or 22, username=username or "git", pkey=key,
                       allow_agent=False, look_for_keys=False, timeout=20)
            ch = cl.get_transport().open_session()
            ch.exec_command(command)
            return _Chan(cl, ch)

    return _Vendor


def push(local_repo, url, refspec="refs/heads/main:refs/heads/main", key=None):
    from dulwich import client, porcelain
    key = pathlib.Path(key or (pathlib.Path.home() / ".ssh" / "id_ed25519"))
    if not key.exists():
        raise FileNotFoundError(f"SSH 私钥不存在：{key}（先生成并把公钥加到托管方）")
    client.get_ssh_vendor = _vendor(key)
    porcelain.push(str(local_repo), url, [refspec.encode() if isinstance(refspec, str) else refspec])
    return url


def main(argv):
    if len(argv) < 2:
        print("用法：python tools/gitpush.py <local_repo> <ssh_url> [refspec]", file=sys.stderr)
        return 2
    local, url = argv[0], argv[1]
    refspec = argv[2] if len(argv) > 2 else "refs/heads/main:refs/heads/main"
    try:
        push(local, url, refspec)
        print(f"✔ 已推送 {local} → {url}（{refspec}）")
        return 0
    except Exception as e:                                          # noqa: BLE001
        print(f"✘ 推送失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
