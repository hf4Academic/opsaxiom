# 评审队列（REVIEW-QUEUE）

> Opus 4.8 在执行中发现的设计缺陷、schema 表达不了的场景、语义存疑点，记录在此，
> 由 Fable 5 在评审轮统一裁决。格式：编号 / 发现于哪个任务 / 问题描述 / 建议方案（可选）。

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

## R-2 (O-2) `verify.expect` / `watch.expect` / `abby_if` 是自由文本

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
