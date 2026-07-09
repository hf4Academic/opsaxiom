# 环境事实注册表（Facts Registry）

> 落实 docs/03 §7.6（评审 F-4）。**权威机器可读清单在 `tools/facts.yaml`**，本文件是它的说明。
> 校验器对未注册的 fact 发 WARN。表达式里跨源比较（如 `rss(KB) > mem_total(MB) * 1024`）
> 依赖这里声明的**单位**才能判断量纲一致。

## 为什么需要它

架构（docs/01 §3）里，环境事实库是"从环境里长出来的指导"的地基。但 facts 一旦被
多个 Skill 引用、还进入表达式做算术，就必须有统一契约：**同一个 fact 到处含义一致、
单位一致**。`memory-leak` 里 `rows[0].rss > mem_total * 1024 * 0.4` 隐含了 rss=KB、
mem_total=MB 的约定——这种约定不能散落在各 Skill 的作者脑子里。

## 字段

| 字段 | 含义 |
|---|---|
| `type` | scalar / list / enum |
| `unit` | bytes / KB / MB / % / count / str / none —— 表达式量纲检查的依据 |
| `collect` | 采集命令示意（真实采集器在连接器层实现） |

## 首批注册（v0.2）

见 `tools/facts.yaml`。当前 13 项，覆盖 host / k8s / network 三域已用到的全部 fact：
os.family, cpu.cores, mem.total(MB), fs.mounts, storage.devices, storage.raid_type,
host.arch, host.virtualization, kernel.version, k8s.context,
device.platform, device.version, bgp.local_as。

## 演进规则

- 新增 Skill 若需要新 fact：**先在 `tools/facts.yaml` 注册**（含 unit），再在 Skill 里引用，
  否则校验器 WARN。
- 单位一致性的**强制**检查（从 WARN 升 ERROR）在表达式量纲推导实现后开启（后续轮次）；
  当前先保证注册表完整与单位声明齐全。
- fact 命名用点分层级 `<域>.<名>`，域名与 taxonomy 的 L1 尽量对齐。
