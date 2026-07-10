# OpsAxiom 容器镜像（V-1）。入口即 opsaxiom。
FROM python:3.12-slim

# 运维排查常用只读工具（导航档本身不需要，但 --real 模式与连接器会用到）
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-client iproute2 procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/opsaxiom
COPY tools/requirements.txt tools/requirements.txt
RUN pip install --no-cache-dir -r tools/requirements.txt

COPY . .
RUN ln -sf /opt/opsaxiom/tools/bin/opsaxiom /usr/local/bin/opsaxiom \
 && for t in /opt/opsaxiom/tools/bin/opsaxiom-*; do ln -sf "$t" "/usr/local/bin/$(basename "$t")"; done \
 && chmod +x /opt/opsaxiom/tools/bin/opsaxiom*

ENV OPSAXIOM_HOME=/root/.opsaxiom
RUN opsaxiom-attest --keygen >/dev/null 2>&1 || true

# 默认进 doctor 自检；覆盖 CMD 可直接跑子命令
ENTRYPOINT ["opsaxiom"]
CMD ["doctor"]
