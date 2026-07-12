#!/usr/bin/env bash
# OpsAxiom 一键安装（V-1）。目标：10 分钟内可用。
#   ./install.sh              # 有网/内网源：创建 venv、装依赖、软链、初始化、自检
#   ./install.sh --offline    # 气隙：从 vendor/wheels 装依赖，不出网
#   ./install.sh --prefix ~/.local/bin   # 软链目标目录（默认 ~/.local/bin）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFLINE=0
PREFIX="${HOME}/.local/bin"
while [ $# -gt 0 ]; do
  case "$1" in
    --offline) OFFLINE=1; shift ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

echo "==> OpsAxiom 安装（root=$ROOT, offline=$OFFLINE）"

# 1) Python 检查
command -v python3 >/dev/null || { echo "🔴 需要 python3" >&2; exit 1; }
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
echo "==> python $PYV"

# 2) venv + 依赖
VENV="$ROOT/.venv"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
. "$VENV/bin/activate"
if [ "$OFFLINE" -eq 1 ]; then
  echo "==> 离线装依赖（vendor/wheels）"
  pip install --no-index --find-links "$ROOT/vendor/wheels" -r "$ROOT/tools/requirements.txt" \
    || echo "🟡 离线依赖不全，核心功能仍可用（缺 cryptography 时 attest 降级 HMAC）"
else
  echo "==> 在线装依赖"
  pip install -q -r "$ROOT/tools/requirements.txt" \
    || echo "🟡 部分依赖装失败，doctor 会指出影响面"
fi

# 3) 软链 opsaxiom-* 进 PATH（用 venv 的 python 执行）
mkdir -p "$PREFIX"
for t in "$ROOT"/tools/bin/opsaxiom*; do
  name="$(basename "$t")"
  ln -sf "$t" "$PREFIX/$name"
done
echo "==> 已软链到 $PREFIX：$(ls "$ROOT"/tools/bin/opsaxiom* | xargs -n1 basename | tr '\n' ' ')"
case ":$PATH:" in
  *":$PREFIX:"*) : ;;
  *) echo "🟡 $PREFIX 不在 PATH，请加入：export PATH=\"$PREFIX:\$PATH\"" ;;
esac

# 4) 初始化 ~/.opsaxiom + 生成签名密钥
OPS_HOME="${OPSAXIOM_HOME:-$HOME/.opsaxiom}"
mkdir -p "$OPS_HOME/sessions" "$OPS_HOME/keys"
"$VENV/bin/python" "$ROOT/tools/bin/opsaxiom-attest" --keygen >/dev/null 2>&1 || true
echo "==> 初始化 $OPS_HOME（会话/密钥目录已建）"

# 5) doctor 自检
echo "==> 运行 doctor 自检"
"$VENV/bin/python" "$ROOT/tools/bin/opsaxiom" doctor || {
  echo "🔴 doctor 报告必需项未通过，请按上方提示修复。"; exit 1; }

echo
echo "✅ 安装完成。试试： opsaxiom diagnose \"磁盘满了但 df 有空间\""
echo "   可选：接一个模型让它更懂人话（不接也全功能可用）——"
echo "        opsaxiom model pull --with-deps   # 内置千问 0.5B（本机离线，≈469MB）"
echo "        opsaxiom model show               # 或看 ollama/远程API/pi 怎么接"
