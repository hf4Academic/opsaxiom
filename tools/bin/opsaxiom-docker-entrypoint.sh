#!/usr/bin/env bash
# 容器入口（full 镜像用）：可选先把内置模型起成 OpenAI 兼容服务并【等就绪】，
# 再 exec 真正的命令。等就绪这一步解决了 pi 连模型的竞态（服务加载 GGUF 要约 10s，
# pi 抢在前面连就报 Connection error）。
#
# 环境开关：
#   OPSAXIOM_AUTOSERVE=1  默认，起 model serve（仅当 llama_cpp 与模型都在时）
#   OPSAXIOM_SERVE_PORT=11435
#   设 =0 关闭（纯导航档 / 只跑子命令时）
set -e

PORT="${OPSAXIOM_SERVE_PORT:-11435}"

_have_local_model() {
  python - <<'PY' 2>/dev/null
import sys
sys.path.insert(0, "/opt/opsaxiom/tools")
import llm
try:
    import llama_cpp  # noqa
except Exception:
    sys.exit(1)
sys.exit(0 if llm.builtin_model_path() else 1)
PY
}

if [ "${OPSAXIOM_AUTOSERVE:-1}" = "1" ] && _have_local_model; then
  echo "[entrypoint] 启动内置模型服务（:$PORT）…"
  opsaxiom model serve --port "$PORT" >/var/log/opsaxiom-serve.log 2>&1 &
  # 等 /v1/models 就绪（最多 ~40s），避免 pi 抢跑
  for i in $(seq 1 40); do
    if python - "$PORT" <<'PY' 2>/dev/null
import sys, urllib.request
urllib.request.urlopen("http://127.0.0.1:%s/v1/models" % sys.argv[1], timeout=2)
PY
    then echo "[entrypoint] 模型服务就绪。"; break; fi
    sleep 1
  done
fi

exec "$@"
