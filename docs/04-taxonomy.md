# 运维知识地图与故障分类树（Taxonomy v0.1）

> Skill 的 `metadata.taxonomy` 必须落在本地图中。L1/L2 由本文件（Fable 设计）固定，
> **L3 及以下由 Opus 4.8 按 §3 的划分规则扩展**，扩展结果回填本文件并经评审合并。

## 1. 设计原则

1. **按"故障/任务的所在层"划分，不按工具划分。**（"Prometheus" 不是分类，"指标缺失"才是）
2. **一个症状一个入口。** 用户报告的是症状（"磁盘满了"），不是根因；L3 叶子以症状/任务命名，
   根因区分放在决策树内部。
3. **两个正交维度**：taxonomy 路径表示"哪里的什么问题"；`kind`（Diagnostic/Change/Hybrid）
   表示"这是排障还是变更"。不要把维度混进路径。
4. **叶子粒度检验**：一个叶子应该对应一个 30 分钟内可走完的决策树。太大拆开，太小合并。

## 2. L1 / L2 地图（固定）

### host —— 主机与操作系统
- `host/cpu`（高负载、软死锁、调度异常）
- `host/memory`（OOM、泄漏、swap 风暴）
- `host/storage`（capacity、iops、文件系统错误、RAID/磁盘硬件）
- `host/network-stack`（连接数、TIME_WAIT、conntrack、DNS 解析）
- `host/process`（僵尸、fd 泄漏、进程异常退出）
- `host/system`（时钟、内核参数、systemd、证书、补丁）
- `host/provision`（装机、探针/agent 部署、基线加固）

### network —— 网络设备与连通性
- `network/reachability`（丢包、时延、路径追踪、MTU）
- `network/routing`（BGP、OSPF、静态路由、路由泄漏）
- `network/switching`（VLAN、STP、MAC 表、端口）
- `network/physical`（光模块、线缆、接口错包）
- `network/security-policy`（ACL、防火墙策略、NAT）
- `network/traffic`（流量异常、DDoS、大象流、环路）
- `network/config-mgmt`（配置审计、基线 diff、批量下发）

### k8s —— 容器与微服务平台
- `k8s/workload`（Pod 异常、CrashLoop、镜像、探针）
- `k8s/scheduling`（Pending、资源配额、亲和性）
- `k8s/networking`（Service、DNS、Ingress、CNI）
- `k8s/storage`（PV/PVC、CSI）
- `k8s/control-plane`（apiserver、etcd、controller）
- `k8s/release`（发布、回滚、HPA、灰度）
- `svc/tracing`（链路慢、超时、重试风暴）——微服务应用层单列

### aicomp —— 智算
- `aicomp/gpu`（XID、ECC、掉卡、温度功耗）
- `aicomp/fabric`（IB/RoCE、NVLink、拓扑）
- `aicomp/collective`（NCCL 性能、allreduce 慢、hang）
- `aicomp/training`（任务 hang、慢节点、checkpoint、利用率）
- `aicomp/scheduling`（slurm/k8s 队列、碎片化）

### middleware —— 中间件与数据库
- `middleware/mysql`、`middleware/redis`、`middleware/kafka`、
  `middleware/es`、`middleware/nginx`、`middleware/rabbitmq`（每个下按症状再分 L3）

### obs —— 可观测性
- `obs/alerting`（告警风暴、降噪、误报）
- `obs/metrics`（指标缺失、采集异常）
- `obs/logging`（日志管道、采集丢失）
- `obs/oncall`（事件时间线、复盘报告生成）

### sec —— 安全运维
- `sec/access`（异常登录、暴破、权限审计）
- `sec/vuln`（漏洞扫描解读、修复）
- `sec/cert`（证书巡检、到期更换）

### proc —— 流程与协作
- `proc/change`（变更单生成）、`proc/incident`（故障报告）、
  `proc/handover`（交接摘要）、`proc/cmdb`（资产更新）

## 3. L3 扩展规则（给 Opus 4.8）

1. 每个 L2 下枚举 3–10 个 L3 叶子；来源优先级：
   高频真实工单场景 > 经典 runbook 文献 > 模型自身知识。
2. 叶子命名用症状/任务名词短语（kebab-case）：`disk-full`、`bgp-neighbor-down`、
   `nccl-allreduce-slow`，不用工具名、不用根因名。
3. 每个叶子附一行"入口症状描述"（用户会怎么说这个问题），用于运行时 Skill 匹配。
4. 拿不准归属的场景放入 `_inbox.md` 待 Fable 评审，不要强行归类。

## 4. Skill 匹配（运行时如何用这棵树）

- 用户输入 → 便宜模型在 L1 做一次分类（8 选 1）→ 在该 L1 的叶子症状描述上做检索匹配
  （embedding + 关键词混合）→ 命中则加载 Skill；多命中给用户选；零命中走升级路径。
- 分层匹配是刻意设计：8 选 1 + 域内检索，比在全库上做开放匹配对弱模型友好得多（R7）。

## 5. L3 全量清单（Opus 4.8 扩展，O-1）

> 格式：`taxonomy 路径` — **入口症状**（用户口语化说法，供运行时匹配）。
> 已有金标准的叶子标 ⭐。归属存疑的场景见 `docs/_inbox.md`。

### 5.1 host
**host/cpu**
- `host/cpu/load-high` — "机器很卡/负载飙到几十/uptime 一堆"
- `host/cpu/steal-high` — "云主机 CPU 被偷/st 很高/性能忽高忽低"
- `host/cpu/softlockup` — "内核 soft lockup/CPU stuck/系统 hang 住"
- `host/cpu/single-core-saturated` — "某个核 100% 其他核空闲/单线程打满"
- `host/cpu/iowait-high` — "iowait 高/CPU 等 IO/系统慢"
- `host/cpu/throttled` — "CPU 降频/cgroup 限流/容器 CPU 被 throttle"

**host/memory**
- `host/memory/oom-kill` — "进程被 OOM Killer 杀了/dmesg 里 Out of memory"
- `host/memory/leak` — "内存只涨不降/怀疑内存泄漏"
- `host/memory/swap-thrash` — "swap 用满/系统巨慢/si so 很高"
- `host/memory/cache-pressure` — "available 内存很低但没进程占用/page cache"
- `host/memory/slab-leak` — "内存被吃但没进程占用/slab 很大"
- `host/memory/hugepage-misconfig` — "大页配置不当/申请大页失败/THP 干扰" — "大页配置不对/应用申请大页失败"

**host/storage**
- `host/storage/capacity/disk-full` ⭐ — "磁盘满了/No space left on device"
- `host/storage/iops-saturated` — "磁盘 IO 打满/iowait 高/读写很慢"
- `host/storage/latency-high` — "磁盘响应慢/await 高但利用率不高"
- `host/storage/fs-readonly` — "文件系统变只读/Read-only file system"
- `host/storage/fs-corruption` — "文件系统报错/需要 fsck/坏块"
- `host/storage/raid-degraded` — "RAID 降级/掉盘/阵列重建"
- `host/storage/iops-latency-mismatch` — "磁盘 await 高但 util 不满/IO 不多却慢"
- `host/storage/mount-failed` — "挂载失败/开机卡在挂载"
- `host/storage/inode-exhausted` — "df 有空间却报 No space/inode 用满"
- `host/storage/mount-failed` — "挂载失败/开机卡挂载/emergency mode"
- `host/storage/smart-failing` — "SMART 告警/dmesg 有 I/O error/怀疑盘要坏"

**host/network-stack**
- `host/network-stack/conntrack-full` — "conntrack table full/新连接建不了"
- `host/network-stack/timewait-flood` — "TIME_WAIT 堆积/端口耗尽/连接失败"
- `host/network-stack/fd-exhausted-socket` — "Too many open files/socket 建不了"
- `host/network-stack/dns-resolve-fail` — "域名解析失败/DNS 超时/间歇解析不了"
- `host/network-stack/dns-flaky` — "DNS 偶发慢/有时 5 秒才通/重试就好/间歇性 Name or service not known"
- `host/network-stack/arp-table-full` — "neighbour table overflow/ARP 表满"
- `host/network-stack/tcp-retrans-high` — "TCP 重传多/吞吐上不去"
- `host/network-stack/packet-drop-local` — "本机丢包/ethtool 计数增长/ring buffer 满"

**host/process**
- `host/process/zombie-flood` — "僵尸进程一堆/defunct/进程表满"
- `host/process/fd-leak` — "进程 fd 泄漏/lsof 数量暴涨"
- `host/process/unexpected-exit` — "进程莫名退出/服务自己挂了/没日志"
- `host/process/thread-explosion` — "线程数暴涨/nproc 超限/pthread_create 失败"
- `host/process/thread-explosion` — "线程数暴涨/pthread_create 失败"
- `host/process/unexpected-exit` — "进程莫名退出没日志/服务自己挂了"
- `host/process/dstate-hang` — "进程卡 D 状态/kill 不掉/不可中断睡眠"

**host/system**
- `host/system/journal-disk-full` — "journal 撑满磁盘/journald 占很大"
- `host/system/clock-drift` — "时间不对/时钟漂移/NTP 不同步"
- `host/system/systemd-unit-failed` — "服务起不来/systemctl failed/开机某单元报错"
- `host/system/ntp-unsynced` — "时间不同步/chrony 不 sync/时间源不可达"
- `host/system/cron-not-firing` — "定时任务没跑/crontab 不生效"
- `host/system/ulimit-exhausted` — "Too many open files/句柄用满"
- `host/system/systemd-restart-loop` — "服务反复重启/start-limit-hit"
- `host/system/dmesg-hardware-error` — "dmesg 有 Hardware Error/MCE/EDAC"
- `host/system/kernel-param-misconfig` — "内核参数不对/sysctl 需要调优"
- `host/system/cert-expiry` — "证书快过期/TLS 证书到期告警"
- `host/system/patch-rollout` — "要批量打补丁/内核升级/安全更新"

**host/provision**
- `host/provision/agent-deploy` — "批量装探针/部署 node_exporter/下发 agent"
- `host/provision/bootstrap` — "新机器初始化/装机后基础配置"
- `host/provision/baseline-drift` — "配置和基线不一致/参数被改过"
- `host/provision/baseline-harden` — "安全基线加固/等保整改/CIS 基线"

### 5.2 network
**network/reachability**
- `network/reachability/packet-loss` — "丢包/网络时好时坏/ping 有丢"
- `network/reachability/arp-storm` — "ARP 报文异常多/CPU 被打高"
- `network/reachability/latency-high` — "网络延迟大/rtt 高/访问慢"
- `network/reachability/mtu-blackhole` — "大包不通小包通/MTU 黑洞/ping 通但传文件卡"
- `network/reachability/asymmetric-route` — "回包走了别的路/非对称路由/单向不通"
- `network/reachability/latency-high` — "网络延迟大/慢在哪一跳"
- `network/reachability/path-trace` — "不知道断在哪一跳/要逐跳排查"

**network/routing**
- `network/routing/bgp-neighbor-down` ⭐ — "BGP 邻居 down/peer 不 Established"
- `network/routing/bgp-route-missing` — "BGP 收不到路由/前缀没通告过来"
- `network/routing/ospf-adjacency-stuck` — "OSPF 邻居卡 ExStart/Init/邻接建不起来"
- `network/routing/route-leak` — "路由泄漏/学到不该有的路由/环路风险"
- `network/routing/route-flapping` — "路由表频繁变动/前缀时有时无"
- `network/routing/vrrp-flapping` — "VRRP 主备频繁切换/网关时通时断"
- `network/routing/default-route-missing` — "出不了外网/默认路由没了" — "默认路由丢了/出不去外网"

**network/switching**
- `network/switching/vlan-misconfig` — "VLAN 不通/跨交换机同网段不通/trunk 没放行"
- `network/switching/stp-loop` — "网络风暴/环路/STP 震荡/端口反复 up down"
- `network/switching/lacp-bond-degraded` — "聚合口带宽减半/LACP 协商失败"
- `network/switching/trunk-vlan-mismatch` — "跨交换机某 VLAN 不通/trunk 允许列表不一致"
- `network/switching/mac-flapping` — "MAC 地址漂移/同 MAC 多端口学习"
- `network/switching/port-err-disabled` — "端口 err-disabled/被自动关闭"

**network/physical**
- `network/physical/optic-fault` — "光模块告警/光衰/收发光功率异常"
- `network/physical/interface-errors` — "接口错包/CRC 错误/input errors 增长"
- `network/physical/optic-power-degrading` — "光功率下降/光模块老化"
- `network/physical/link-flap` — "接口 up down 抖动/链路不稳"

**network/security-policy**
- `network/security-policy/acl-block` — "被 ACL 拦了/策略不通/加白名单"
- `network/security-policy/nat-issue` — "NAT 不对/映射不通/源地址不对"
- `network/security-policy/nat-session-full` — "NAT 会话表满/新连接建不了"
- `network/security-policy/dhcp-snooping-drop` — "客户端拿不到 IP/DHCP 被丢"
- `network/security-policy/port-security-violation` — "端口安全违规/接入不通"
- `network/security-policy/firewall-session` — "防火墙会话满/策略命中排查"

**network/traffic**
- `network/traffic/anomaly-detect` — "流量异常/突发大流量/带宽打满不知道谁"
- `network/traffic/ddos-suspect` — "疑似被攻击/大量异常连接/DDoS"
- `network/traffic/elephant-flow` — "个别大象流占满带宽/单流打满"
- `network/traffic/qos-drops` — "某类流量丢包/QoS 队列 drop"
- `network/traffic/broadcast-storm` — "广播风暴/广播包异常多"

**network/config-mgmt**
- `network/config-mgmt/config-audit` — "全网配置审计/一致性检查"
- `network/config-mgmt/config-drift` — "配置被改过/和基线不一致/未保存"
- `network/config-mgmt/baseline-diff` — "配置和基线对比/谁改了配置"
- `network/config-mgmt/bulk-deploy` — "批量下发配置/多台设备统一改"

### 5.3 k8s / svc
**k8s/workload**
- `k8s/workload/crashloop` — "Pod 一直重启/CrashLoopBackOff"
- `k8s/workload/image-pull-fail` — "拉不了镜像/ImagePullBackOff/ErrImagePull"
- `k8s/workload/oomkilled` — "Pod 被 OOMKilled/容器内存超限"
- `k8s/workload/probe-failing` — "健康检查失败/readiness 不过/liveness 重启"
- `k8s/workload/pod-evicted` — "Pod 被驱逐/Evicted/节点压力"

**k8s/scheduling**
- `k8s/scheduling/pending-unschedulable` — "Pod 一直 Pending/调度不上去"
- `k8s/scheduling/resource-quota-exceeded` — "配额超了/建不了资源/quota exceeded"
- `k8s/scheduling/node-notready` — "节点 NotReady/节点掉了"
- `k8s/scheduling/taint-toleration` — "污点容忍不匹配/调度不到指定节点"

**k8s/networking**
- `k8s/networking/service-no-endpoints` — "Service 访问不通/没有 endpoints"
- `k8s/networking/dns-fail` — "集群内 DNS 解析失败/CoreDNS 问题"
- `k8s/networking/ingress-503` — "Ingress 502/503/外部访问不通"
- `k8s/networking/networkpolicy-block` — "NetworkPolicy 拦了/Pod 间不通"

**k8s/storage**
- `k8s/storage/pvc-pending` — "PVC 一直 Pending/绑不上 PV"
- `k8s/storage/volume-mount-fail` — "挂卷失败/FailedMount/多重挂载冲突"

**k8s/control-plane**
- `k8s/control-plane/apiserver-slow` — "kubectl 很慢/apiserver 超时/429"
- `k8s/control-plane/etcd-unhealthy` — "etcd 不健康/告警/空间满"

**k8s/release**
- `k8s/release/rollout-stuck` — "发布卡住/rollout 不进/新版本起不来"
- `k8s/release/rollback` — "要回滚上一个版本/发新版出问题"
- `k8s/release/hpa-not-scaling` — "HPA 不扩容/指标有但不动"

**svc/tracing**
- `svc/tracing/latency-spike` — "接口突然变慢/P99 飙高/慢在哪个服务"
- `svc/tracing/error-rate-spike` — "错误率上升/5xx 变多/哪个下游挂了"
- `svc/tracing/retry-storm` — "重试风暴/雪崩/下游被打挂"

### 5.4 aicomp
**aicomp/gpu**
- `aicomp/gpu/xid-error` — "GPU XID 报错/dmesg 有 NVRM Xid"
- `aicomp/gpu/ecc-error` — "GPU ECC 错误/显存报错"
- `aicomp/gpu/fell-off-bus` — "掉卡/nvidia-smi 少了卡/GPU is lost"
- `aicomp/gpu/thermal-throttle` — "GPU 降频/温度过高/功耗墙"
- `aicomp/gpu/driver-mismatch` — "Failed to initialize NVML/Driver library version mismatch/CUDA insufficient"

**aicomp/fabric**
- `aicomp/fabric/ib-link-down` — "IB 链路 down/InfiniBand 端口异常"
- `aicomp/fabric/roce-packet-loss` — "RoCE 丢包/PFC 配置/网络重传高"
- `aicomp/fabric/nvlink-degraded` — "NVLink 降速/带宽不对/连接异常"

**aicomp/collective**
- `aicomp/collective/nccl-allreduce-slow` — "NCCL allreduce 慢/通信带宽打不满"
- `aicomp/collective/nccl-hang` — "训练 hang 在通信/NCCL 卡住不动"
- `aicomp/collective/nccl-init-fail` — "NCCL 初始化失败/建不了通信组"

**aicomp/training**
- `aicomp/training/job-hang` — "训练任务卡住/loss 不动/进程在但没进展"
- `aicomp/training/slow-node` — "个别节点拖慢/慢节点定位/木桶效应"
- `aicomp/training/checkpoint-recovery` — "checkpoint 恢复/断点续训/保存失败"
- `aicomp/training/gpu-util-low` — "GPU 利用率低/算力浪费/打不满"

**aicomp/scheduling**
- `aicomp/scheduling/queue-stuck` — "任务排队不跑/slurm pending/资源碎片"
- `aicomp/scheduling/gpu-fragmentation` — "GPU 碎片化/整机分配不出来"

### 5.5 middleware
**middleware/mysql**
- `middleware/mysql/slow-query` — "MySQL 慢/慢查询多/CPU 高"
- `middleware/mysql/replication-lag` — "主从延迟大/从库落后"
- `middleware/mysql/replication-broken` — "主从断了/复制报错/Slave 停了"
- `middleware/mysql/connections-exhausted` — "连接数满/Too many connections/连接池获取超时/1040"
- `middleware/mysql/deadlock` — "死锁/lock wait timeout"

**middleware/redis**
- `middleware/redis/bigkey` — "Redis 有大 key/某 key 巨大/阻塞"
- `middleware/redis/memory-full` — "Redis 内存满/OOM/开始淘汰 key"
- `middleware/redis/slow-command` — "Redis 变慢/慢查询/latency 高"
- `middleware/redis/hotkey` — "热 key/单个 key QPS 过高/分片不均"

**middleware/kafka**
- `middleware/kafka/consumer-lag` — "Kafka 积压/消费跟不上/lag 高"
- `middleware/kafka/under-replicated` — "副本不同步/URP/ISR 收缩"
- `middleware/kafka/broker-down` — "broker 挂了/分区 leader 选举"

**middleware/es**
- `middleware/es/cluster-red` — "ES 集群 red/yellow/分片未分配"
- `middleware/es/unassigned-shards` — "分片分配不了/unassigned"
- `middleware/es/jvm-heap-pressure` — "ES 堆内存压力/GC 频繁/慢"

**middleware/nginx**
- `middleware/nginx/upstream-5xx` — "nginx 502/504/上游超时"
- `middleware/nginx/worker-connections-full` — "worker_connections 不够/拒绝连接"

**middleware/rabbitmq**
- `middleware/rabbitmq/queue-backlog` — "队列堆积/消息消费不掉"
- `middleware/rabbitmq/memory-alarm` — "RabbitMQ 内存告警/流控/阻塞发布"

### 5.6 obs
- `obs/alerting/alert-storm` — "告警风暴/一堆告警/降噪"
- `obs/alerting/false-positive` — "误报/告警不准/阈值要调"
- `obs/metrics/missing` — "监控没数据/指标断了/采集不到"
- `obs/metrics/target-down` — "exporter 挂了/target down/抓不到"
- `obs/logging/pipeline-loss` — "日志丢了/采集管道断/日志不全"
- `obs/oncall/incident-timeline` — "生成事件时间线/整理故障过程"
- `obs/oncall/postmortem-draft` — "写复盘报告/故障总结初稿"

### 5.7 sec
- `sec/access/abnormal-login` — "异常登录/可疑登录/异地登录排查"
- `sec/access/bruteforce` — "暴力破解/大量失败登录/被爆破"
- `sec/access/privilege-audit` — "权限审计/谁有 sudo/越权检查"
- `sec/vuln/scan-triage` — "漏洞扫描结果解读/怎么修/优先级"
- `sec/vuln/patch-verify` — "确认漏洞是否已修/补丁验证"
- `sec/cert/expiry-inventory` — "证书到期巡检/全网证书清点"

### 5.8 proc
- `proc/change/ticket-gen` — "生成变更单/写变更申请"
- `proc/incident/report-gen` — "生成故障报告/事故报告"
- `proc/handover/shift-summary` — "值班交接摘要/交班总结"
- `proc/cmdb/asset-reconcile` — "更新 CMDB/资产核对/配置项同步"

### 5.9 O-3 生成范围排序（host 域 top-20，按预估工单频率）

高频优先（1–10）：disk-full⭐、load-high、oom-kill、memory-leak、iops-saturated、
fs-readonly、systemd-unit-failed、dns-resolve-fail、zombie-flood、fd-leak。
次高频（11–20）：conntrack-full、timewait-flood、cpu-steal-high、clock-drift、
softlockup、cert-expiry、dstate-hang、swap-thrash、agent-deploy、raid-degraded。
（disk-full 已是金标准，O-3 实际新增 19 个；排序理由见各 commit message。）
