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
