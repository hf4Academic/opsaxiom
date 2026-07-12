# OpsAxiom 容器镜像（多阶段，按需选重量）。
#
#   docker build --target core -t opsaxiom:core .     # 纯导航档，气隙友好（~250MB）
#   docker build --target llm  -t opsaxiom:llm  .     # + 内置千问0.5B + model serve（~1.2GB）
#   docker build            -t opsaxiom:full .        # + node22 + pi 智能入口（默认，~1.4GB）
#
# 运行：
#   docker run -it opsaxiom:full                      # pi 智能入口（自动起模型服务并等就绪）
#   docker run -it opsaxiom:full opsaxiom classic     # 强制老 REPL
#   docker run --rm opsaxiom:core diagnose "磁盘满了"  # 一次性子命令
#
# 约束：绝不在构建期生成签名私钥（F-13：烤进镜像=所有容器共享同一私钥）；
# 密钥由 attest 在容器内首次签名时惰性生成。

# ───────────────────────── pi 构建阶段（node + pi）─────────────────────────
FROM node:22-bookworm-slim AS pi-builder
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
RUN npm install --prefix /opt/pi-agent @earendil-works/pi-coding-agent \
 && npm cache clean --force

# ───────────────────────── core：opsaxiom + python 依赖 ─────────────────────
FROM python:3.12-slim AS core
# 运维排查常用只读工具（导航档不需要，--real 与连接器会用）
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-client iproute2 procps ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/opsaxiom
COPY tools/requirements.txt tools/requirements.txt
RUN pip install --no-cache-dir -r tools/requirements.txt
COPY . .
RUN ln -sf /opt/opsaxiom/tools/bin/opsaxiom /usr/local/bin/opsaxiom \
 && for t in /opt/opsaxiom/tools/bin/opsaxiom-*; do \
      case "$t" in *.sh) ;; *) ln -sf "$t" "/usr/local/bin/$(basename "$t")";; esac; done \
 && chmod +x /opt/opsaxiom/tools/bin/opsaxiom*
ENV OPSAXIOM_HOME=/root/.opsaxiom \
    OPSAXIOM_ROOT=/opt/opsaxiom
ENTRYPOINT ["opsaxiom"]
CMD ["doctor"]

# ───────────────────────── llm：+ llama.cpp server + 千问0.5B ───────────────
FROM core AS llm
# 编译 llama-cpp-python[server]；编译器用完即删（保持镜像瘦）
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git \
 && CMAKE_ARGS="-DGGML_NATIVE=OFF" pip install --no-cache-dir "llama-cpp-python[server]" \
 && apt-get purge -y build-essential cmake git \
 && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
# 烤入内置模型（WITH_MODEL=0 可跳过，改运行时 opsaxiom model pull）
ARG WITH_MODEL=1
ARG MODEL_URL=https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/master/qwen2.5-0.5b-instruct-q4_k_m.gguf
RUN if [ "$WITH_MODEL" = "1" ]; then \
      mkdir -p /root/.opsaxiom/models && \
      python -c "import urllib.request; urllib.request.urlretrieve('$MODEL_URL', '/root/.opsaxiom/models/qwen2.5-0.5b-instruct-q4_k_m.gguf')" && \
      printf 'enabled: true\nbackend: builtin\n' > /root/.opsaxiom/model.yaml ; \
    fi
CMD ["doctor"]

# ───────────────────────── full：+ node22 + pi 智能入口 ─────────────────────
FROM llm AS full
# 从 pi-builder 搬运 node 运行时与已装好的 pi（同为 bookworm，ABI 兼容）
COPY --from=pi-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=pi-builder /opt/pi-agent /opt/pi-agent
RUN ln -sf /opt/pi-agent/node_modules/.bin/pi /usr/local/bin/pi
# 容器入口：先起模型服务并等就绪（解 pi 连模型竞态），再进 opsaxiom（TTY 下自动进 pi）
RUN chmod +x /opt/opsaxiom/tools/bin/opsaxiom-docker-entrypoint.sh
ENTRYPOINT ["/opt/opsaxiom/tools/bin/opsaxiom-docker-entrypoint.sh"]
CMD ["opsaxiom"]
