# Opus 4.8 任务书

# 第二轮（Fable 布置，2026-07-09）

> 通用要求同第一轮：读 HANDOFF → 小步提交（前缀 `[P-n]`）→ 疑问进 REVIEW-QUEUE 不改设计 →
> 全部完成后更新 HANDOFF 并提醒切回 Fable。规范依据：`docs/03 §7`（v0.2 决议）与
> REVIEW-QUEUE 第一轮裁决。

## P-1 实施 schema v0.2（最高优先，其余条目依赖）
- schema/skill.schema.json 与校验器：`metadata.params`、`ask.binds`、`verify.assert+note`、
  S11（回滚空转检测：rollback.run 归一后若只含 echo/注释 → ERROR，`human_only` + `rollback.advisory: true` 豁免）。
- exprlang：_FUNCS 增加 `avg`/`sum`（验证器与求值器同步），模板渲染统一到字段引用文法（docs/03 §7.4）。
- **迁移全部 31 个 Skill**：补 params 声明、ask 补 binds、verify.expect → assert+note、
  拍平变量（rows0_comm 等）改为下标路径。迁移完成后 **S9 升为 ERROR**，全量校验必须全绿。
- 新建 `docs/06-facts.md` facts 注册表（首批清单见 docs/03 §7.6），实现跨源单位一致性告警。

## P-2 修复评审 F 系列
- F-3：iops-saturated 退化分支节点（区分出口或删除）。
- F-5：k8s exec 类检查补"容器可能没有该工具"的 cautions 与降级命令。
- F-7：conntrack-full 字段改名 ct_count/ct_max。
- 顺带把上述三条教训写进一个新文件 `docs/07-authoring-rules.md`（Skill 生成规范：
  设备名不写死、字段不与函数同名、exec 不假设容器工具、count>=k 抗尖峰模式……
  第一轮所有踩坑都沉淀进去，这是给未来批量生成当 prompt 用的）。

## P-3 实现 opsaxiom-deploy（agent-deploy 依赖，参照 quarantine 的品质：可测、幂等、可卸载）

## P-4 实现 tools/promote.py（maturity 流水线）
- `promote <skill>`：核验 sim 结果 + S8 → 写 maturity 与 provenance 证据；`demote` 同理。
- 把 disk-full 的手动晋级重放一遍作为首个测试用例（结果应一致）。

## P-5 仿真覆盖扩面
- 为 host 域至少 10 个、k8s 域至少 5 个 Skill 编写可执行 sim 场景（复用 run_sim.py 的
  node_ctx 机制），通过者由 P-4 流水线晋级 sim_verified。
- k8s 的 transaction 型回滚（rollout undo）设计一个真实往返验证方案（无集群环境时用
  kubectl mock/录制回放，方案先写进 sim/README 再实现）。

## P-6 network 域 Skill 包（10 个，按 docs/04 §5.2 高频叶子）
- 每个命令必须过三平台语法树；语法树未覆盖的命令先扩 tools/syntax/*.yaml（扩树属允许操作，
  但每条新前缀在 commit message 里给出厂商文档依据）。
- containerlab/真实设备仿真本轮仍不做（环境无 docker），bgp 金标准继续维持 draft。

进度勾选区（Opus 更新）：
- [x] P-1  - [x] P-2  - [x] P-3  - [x] P-4  - [x] P-5  - [x] P-6

全部完成。校验 41/41、pytest 130/130、仿真 19/19 全绿。41 个 Skill(host20/k8s10/network11)，
17 个 sim_verified。新缺口 R-5(解析器字段契约)、R-6(S8 诊断类精化，待追认)。

---

# 第一轮（已完成，存档）

> 执行者：Claude Opus 4.8。开始前先读 `HANDOFF.md` 规定的阅读顺序。
> 通用要求：每完成一条 → git commit（message 前缀 `[O-n]`）→ 勾选本文件对应条目。
> 你产出的所有 skill.yaml 的 `metadata.provenance.generated_by` 写 `claude-opus-4-8`，
> `maturity` 一律为 `draft`（晋级由流水线核算，你无权声明）。
> 发现设计缺陷/schema 表达不了的场景：记入 `REVIEW-QUEUE.md`，不要自行改设计。

## O-1 扩展分类体系 L3 ✅优先级最高，后续条目依赖它
- 按 `docs/04-taxonomy.md` §3 的规则，为全部 8 个 L1 域的每个 L2 枚举 3–10 个 L3 叶子。
- 每个叶子附一行"入口症状描述"（用户口语化的说法）。
- 产出：直接回填 `docs/04-taxonomy.md`（新增 §5 "L3 全量清单"），归类存疑的放 `docs/_inbox.md`。

## O-2 实现 Skill 校验器（tools/validate）
- Python，单命令：`python tools/validate.py skills/` 全量校验。
- 两层：(a) 按 `schema/skill.schema.json` 结构校验；(b) 语义规则 S1–S10（docs/03 §4）。
  - S5 的受限表达式语言：先实现保守子集（字段引用、比较、and/or/not、max/min/count/any/all、delta），
    解析失败一律报错——宁可严不可松。
  - S6 语法树校验：本轮先做接口占位（返回 warning 而非 error），真正的语法树在 O-5。
- 两个金标准 Skill 必须通过校验；如果它们本身有不符合 schema 之处，
  **以 schema 为准修正金标准的表层格式，语义疑问进 REVIEW-QUEUE**。
- 附 pytest 用例（合法/非法样例各 ≥5）。

## O-3 host 域批量生成 20 个 Skill
- 以 `skills/host/disk-full/skill.yaml` 为模板与质量基准，覆盖 O-1 产出的 host 域 L3
  中最高频的 20 个叶子（你判断频率，排序理由写进 commit message）。
- 硬性要求：全部通过 O-2 校验器；每个 Skill ≥2 个 tests 场景（场景文件本轮只写 YAML 描述，
  仿真执行环境在 O-6）；每个 action 节点的 cautions ≥1 条且必须是"实战级"提醒
  （像金标准那样写坑，不写废话）。
- 产出目录：`skills/host/<slug>/skill.yaml`。

## O-4 k8s 域批量生成 10 个 Skill
- 同 O-3 要求，模板参考两个金标准的结合（k8s 命令 + 多分支诊断）。
- 注意：k8s 的 rollback 优先用平台原生事务能力（`kubectl rollout undo`、`kubectl apply` 幂等回放），
  对应 rollback.type=transaction 或 snapshot。

## O-5 解析器库与命令语法树骨架（tools/parsers, tools/syntax）
- 解析器：接入 ntc-templates（作为依赖，不要复制代码）；为金标准里引用的
  `table/df-v1`、`table/df-inode-v1`、`table/du-v1` 写自研解析器 + 测试。
- 语法树：定义平台命令前缀树的数据格式（YAML），先手工覆盖两个金标准 Skill 用到的
  全部 cisco_ios/huawei_vrp/junos/linux 命令，并让 O-2 的 S6 从占位变为真实校验。

## O-6 仿真验证环境 v0（sim/）
- Docker Compose 起一个 Linux 靶机容器，实现三个故障注入场景脚本，对应
  disk-full 的三个 tests（日志膨胀 / 删除未释放 / inode 耗尽）。
- 实现最小执行器：读 skill.yaml → 在靶机按 expect_path 走树 → 断言路径与回滚
  （`rollback_assert: true` 的场景必须实际执行 action + rollback 并比对状态）。
- 顺带实现 `opsagent-quarantine`（move/restore/purge 三个子命令）——金标准依赖它。
- 网络设备仿真（containerlab）本轮**不做**，留给下一轮。

## O-7 收尾与交接
- 更新 `HANDOFF.md` 当前状态：已完成条目、REVIEW-QUEUE 摘要、你建议 Fable 优先评审什么。
- 确保 `python tools/validate.py skills/` 全绿、pytest 全绿，结果贴进 HANDOFF。
- **在给用户的最后回复中明确提醒："本轮任务完成，请切换回 Fable 5 进行对抗评审。"**

---
进度勾选区（Opus 更新）：
- [x] O-1  - [x] O-2  - [x] O-3  - [x] O-4  - [x] O-5  - [x] O-6  - [x] O-7

全部完成。校验器全量 31/31 过，pytest 90/90 过，三条仿真场景全过（含真实回滚往返）。
