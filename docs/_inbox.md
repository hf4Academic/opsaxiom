# 分类归属待议（_inbox）

> O-1 扩展 L3 时归属存疑的场景，留给 Fable 评审裁决，不强行归类（docs/04 §3 规则4）。

- **"网络慢"到底属于 host 还是 network？** 现按"本机网络栈问题→host/network-stack，
  链路/设备问题→network/reachability"切分，但用户报障时往往分不清。建议运行时先跑一个
  分流探针（本机 ping 网关 vs ping 外部）再定向，而非在 taxonomy 层硬分。
- **容器内的主机类问题**（容器 OOM vs 宿主 OOM）：现放 k8s/workload/oomkilled，
  但根因可能在宿主 host/memory。跨域 Skill 是否需要"转诊"机制？记 REVIEW-QUEUE 待议。
- **`svc/tracing` 挂在 k8s 的 L1 下是否合适？** 微服务不一定跑在 k8s 上（也可能是裸机/VM）。
  可能需要把 svc 提升为独立 L1。暂留观察。
- **智算与普通 host 的边界**：GPU 节点的 CPU/磁盘问题走 host 还是 aicomp？
  现约定：非 GPU 相关走 host，GPU/IB/训练相关走 aicomp。
