"""
pi 入口探测与启动（N-3）。

策略（发起人裁决：pi 是智能入口，Python REPL 是零依赖兜底——R3 不破）：
  裸敲 opsaxiom：
    1. OPSAXIOM_ENTRY=classic → 直接老 REPL；
    2. 否则探测 pi 可用（pi 可执行 + node>=22.19）→ exec pi -e tools/pi/opsaxiom.ts；
    3. 探测不到 → 老 REPL（一字不变，气隙/无 node 环境无感）。
  `opsaxiom classic` 强制老入口；`opsaxiom pi` 强制 pi（不可用时报缺什么）。

探测顺序（node 与 pi 各自独立）：
  node：PATH 里的 node；不够新再试 ~/.local/node22/bin/node（install 脚本落点）。
  pi：PATH 里的 pi；再试 ~/.local/pi-agent/node_modules/.bin/pi（npm --prefix 落点）。
"""
import os
import pathlib
import shutil
import subprocess

MIN_NODE = (22, 19, 0)


def _node_version(node):
    try:
        v = subprocess.run([node, "--version"], capture_output=True, text=True,
                           timeout=5).stdout.strip().lstrip("v")
        return tuple(int(x) for x in v.split(".")[:3])
    except Exception:
        return None


def find_node():
    """返回满足版本的 node 路径，或 None。"""
    cands = []
    p = shutil.which("node")
    if p:
        cands.append(p)
    cands.append(str(pathlib.Path.home() / ".local" / "node22" / "bin" / "node"))
    for c in cands:
        if pathlib.Path(c).exists():
            v = _node_version(c)
            if v and v >= MIN_NODE:
                return c
    return None


def find_pi():
    """返回 pi 可执行路径，或 None。"""
    p = shutil.which("pi")
    if p:
        return p
    local = (pathlib.Path.home() / ".local" / "pi-agent" / "node_modules"
             / ".bin" / "pi")
    return str(local) if local.exists() else None


def probe():
    """返回 (可用?, node路径|缺口说明, pi路径|None)。"""
    node = find_node()
    if not node:
        return False, "缺 node >= 22.19（npmmirror 下载解压到 ~/.local/node22 即可）", None
    pi = find_pi()
    if not pi:
        return False, ("缺 pi（用 node22 的 npm 装：npm install --prefix "
                       "~/.local/pi-agent @earendil-works/pi-coding-agent）"), None
    return True, node, pi


def launch(root, extra_args=None):
    """exec 进 pi（不返回）。node22 目录进 PATH（pi 的 shebang 要新 node）。"""
    ok, node, pi = probe()
    if not ok:
        return node                      # 返回缺口说明（调用方打印并回落）
    env = dict(os.environ)
    env["OPSAXIOM_ROOT"] = str(root)
    env["PATH"] = str(pathlib.Path(node).parent) + os.pathsep + env.get("PATH", "")
    ext = str(pathlib.Path(root) / "tools" / "pi" / "opsaxiom.ts")
    argv = [pi, "-e", ext] + list(extra_args or [])
    os.execvpe(pi, argv, env)            # 不返回
