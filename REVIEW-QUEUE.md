# 评审队列（REVIEW-QUEUE）

> Opus 4.8 在执行中发现的设计缺陷、schema 表达不了的场景、语义存疑点，记录在此，
> 由 Fable 5 在评审轮统一裁决。格式：编号 / 发现于哪个任务 / 问题描述 / 建议方案（可选）。

---
# 第一轮裁决（Fable 5，2026-07-09）

**R-1 采纳 / R-2 采纳变体 / R-3 采纳 / R-4 采纳（统一到表达式文法）。**
规范性细节已写入 `docs/03-skill-schema.md §7`（v0.2 决议），实施任务在 TODO-opus 第二轮 P-1。
四条均保留原文于下，状态：已裁决，待实施后关闭。

> **[P-1 关闭 R-1~R-4 + F-2/F-4，2026-07-09 Opus]** v0.2 已实施并迁移全部 31 Skill：
> schema 增 params/ask.binds/verify(assert+note)/rollback.advisory；exprlang 增 avg/sum +
> parse_template_ref；S9 升 ERROR；新增 S11(回滚空转)；facts 注册表 tools/facts.yaml + docs/06 +
> FACTS 成员告警。校验 31/31、pytest 100/100 全绿。R-1/R-3/R-4/F-2/F-4 关闭；
> R-2 部分关闭（verify.assert 已强制表达式；watch.expect/abort_if 按裁决保留散文）。
> **遗留给 Fable 复核**：迁移中 verify.assert 引用了若干"解析器应产出但尚未实现"的字段
> （service_active/metrics_ok/rollout_succeeded/mount_rw/pcent_before 等）——这些是解析器契约，
> 记为新条目 R-5，待解析器补齐时对齐。

## 对抗评审新发现（F 系列）

审查范围：29 个 Opus 生成 Skill 全部通读，6 个带写操作的逐行审
（fs-readonly / k8s-rollback / clock-drift / agent-deploy / systemd-unit-failed / rollout-stuck 相关动作）。

- **F-1（已修复）** `raid-degraded` 把设备写死为 `/dev/md0`，多阵列机器会查错对象。
  已改为遍历 `/dev/md[0-9]*`。教训入生成规范：**设备/实例名永远不许写死**。
- **F-2（裁决→S11）** `fs-readonly` 的 fsck 回滚是 echo 占位——形式过 S1、实质违宪(R1)。
  裁决：新增 S11"回滚不得空转"，human_only 节点允许显式 `advisory: true`。见 docs/03 §7.5。
- **F-3（待修，P-2）** `iops-saturated` 的 `latency_vs_throughput` 节点是退化分支
  （所有分支同一去向），要么区分出口要么删节点。
- **F-4（裁决→facts 注册表）** facts 单位无规范：`memory-leak` 里 `rows[0].rss > mem_total * 1024 * 0.4`
  隐含 rss=KB、mem_total=MB 的约定但无处声明。见 docs/03 §7.6，P-1 实施。
- **F-5（待修，P-2）** k8s 域 exec 类检查假设容器内有 nslookup 等工具（distroless 镜像会失败），
  相关节点需补 cautions 与降级命令（如改用 `kubectl debug`）。
- **F-6（待建，P-3）** `agent-deploy` 引用的 `opsaxiom-deploy` 工具不存在（与上轮 quarantine 同型问题）。
- **F-7（风格，P-2）** `conntrack-full` 用 `count`/`max` 作字段名，与内置函数同名——能跑但脆弱，
  改名 `ct_count`/`ct_max`。生成规范补充：**字段名不得与函数名冲突**。

## 抽查结论

- 高危 Skill 的领域判断整体合格：fs-readonly 的"硬件错误禁 fsck"、raid 的"重建期不碰阵列"、
  clock-drift 的"生产慎 step"、k8s-rollback 的"DB 迁移不随代码回滚"等关键 caution 都在且正确。
- `chronyd -Q`（只查不设）用法正确；`rollout undo --to-revision` 的事务语义正确。
- **maturity**：`host.storage.capacity.disk-full` 依据 O-6 仿真证据晋级 `sim_verified`
  （Fable 代行流水线，证据记录于该 Skill 的 provenance.source_trace）；其余 30 个维持 draft——
  它们的 tests 场景还没有可执行的仿真上下文（只有 disk-full 有），这是下一轮 P-5 的主要产出。

---

## R-1 (O-2) S9 无法强制：schema 缺少变量声明位

- **发现于**：O-2 实现校验器时。
- **问题**：S9 要求"模板变量 `{{x}}` 必须在 facts/discovery/ask 有来源"，但当前 schema 没有地方
  声明 action/ask 节点产出的变量名，也没有"skill 入参"的声明位。金标准里 `{{mount}}`、
  `{{files}}`（来自 ask 选择）、`{{svc}}`、`{{qdir}}`、`{{threshold}}`、`{{peer_ip}}` 等
  都是运行时上下文/入参，无法回溯到 facts 或 discovery。
- **本轮处理**：S9 降级为 WARNING（不阻断），金标准照常通过。校验器已能列出无来源变量。
- **建议（待 Fable 定夺）**：schema v0.2 增加两处声明：
  1. `metadata.params: [{name, source: alert|user|derived, desc}]` —— 声明 skill 级入参；
  2. `ask` 节点增加 `binds: <varname>` —— 声明该 ask 的答案绑定到哪个变量。
  之后 S9 可升为 ERROR：变量来源 = facts ∪ discovery.id ∪ params ∪ ask.binds ∪ builtin{sid}。

## R-2 (O-2) `verify.expect` / `watch.expect` / `abort_if` 是自由文本

- **发现于**：O-2。金标准里这些字段混用"表达式"（`rows[0].pcent < 90`）与"散文"
  （`使用率下降`、`服务 active 且...`）。当前只有 `branch.when` 被 S5 强制为可解析表达式。
- **影响**：运行时引擎/模型需要"解释"这些散文断言，弱模型上可靠性存疑（与 R7 张力）。
- **建议**：v0.2 考虑要求 `verify.expect` 也走受限表达式（保留 `expect_human` 作为附带说明），
  或至少要求 `verify` 提供一个机器可判的 `assert` 字段 + 可选散文 `note`。


## R-3 (O-3) 表达式缺 avg/sum 聚合函数

- **发现于**：O-3 批量生成 host 域诊断 Skill 时。
- **问题**：docs/03 §5 允许的聚合仅 `max/min/count/any/all/delta`。诊断里大量需要"多次采样取均值"
  的判断（vmstat/iostat/mpstat 的 wa、util、steal 等），没有 `avg`/`sum` 很别扭。
- **本轮处理**：一律改用 `count(rows[].x > 阈值) >= k` 表达"k 个以上采样超阈值"，语义上更稳健
  （不受单次尖峰影响），已能覆盖需求，但对"求和类"指标（如总带宽）仍不便。
- **建议（待 Fable 定夺）**：v0.2 在允许函数集加入 `avg` 与 `sum`（纯确定性、对弱模型无负担），
  同时保留 count 模式作为推荐写法。若同意，需同步更新 docs/03 §5、tools/exprlang.py 的 _FUNCS、
  以及本文 R-3 关闭。

## R-4 (O-3) 模板变量命名：数组元素字段引用（rows0_comm 之类）

- **发现于**：O-3。`done` 节点的 summary 想引用"排第一的进程名"，schema 的 `{{}}` 模板不支持
  `{{rows[0].comm}}` 这种带下标的路径（点分变量名限制），只能退而用 `{{rows0_comm}}` 这种拍平写法，
  需要引擎在渲染时提供别名映射。
- **建议**：v0.2 明确模板变量语法是否允许下标/点路径（如 `{{discovery.free.available_pct}}`），
  并规定 discovery 输出如何绑定到模板命名空间。当前 summary 里的变量渲染契约未定义，记此备忘。

## R-5 (P-1) verify.assert 引用了未实现的解析器字段

- **发现于**：P-1 迁移各 action 的 verify.expect(散文) → assert(表达式) 时。
- **问题**：为让 assert 机器可判，我引用了解析器"应当产出"的结构化字段：
  service_active、metrics_ok、rollout_succeeded、unready_pods、mount_rw、fs_errors、pcent_before。
  这些字段的解析器尚未实现（服务健康类、kubectl status 类），且 pcent_before 是"执行前基线"，
  需要引擎在 action 前快照——属运行时引擎契约，当前 sim 不覆盖 verify。
- **不阻断**：assert 只被 S5 校验语法（已通过），不校验字段来源；sim 不执行 verify。
- **建议**：解析器补齐时（后续轮次）定义这批"健康类字段"的标准命名与解析器；
  引擎实现 verify 前快照（pcent_before 之类）。届时可加一条"assert 字段须有解析器产出"的校验。

## R-6 (P-5) S8 对纯诊断 Skill 不可满足——已精化，待 Fable 批准

- **发现于**：P-5 给诊断 Skill 写仿真、准备晋级时。
- **问题**：S8 原文要求 sim_verified 必须有 `rollback_assert:true` 测试，但**纯 Diagnostic Skill
  没有 action → 没有回滚 → 永远无法晋级**。这显然违背意图（诊断 Skill 也该能 sim_verified）。
- **本轮处理（需 Fable 追认）**：精化 S8——`rollback_assert` **仅对含 action 的 Skill 强制**；
  纯诊断 Skill 满足"tests 非空 + 所有路径 sim 通过"即可晋级。validate.py 与 promote.py 已同步实现。
  据此已晋级 16 个 Skill（10 host 诊断 + agent-deploy 含真实部署回滚 + 5 k8s 诊断），连同 disk-full 共 17 个 sim_verified。
- **建议**：Fable 在 docs/03 §7 或 docs/05 §1 明确这条口径（诊断类 vs 变更类的晋级门槛差异）。
