# 模型交接协议（HANDOFF）

> **任何模型接手本仓库的第一件事：读完本文件。** 本文件永远反映当前状态与下一步。
> 每个模型在结束自己的工作阶段前，必须更新本文件的"当前状态"与"交接给谁"。

## 阅读顺序（新接手模型必读，按序）

1. `HANDOFF.md`（本文件）—— 当前状态与你的任务入口
2. `docs/00-golden-rules.md` —— 宪法，全部 12 条，不可违反
3. 与你任务相关的设计文档（见下方任务指引）
4. `skills/host/disk-full/skill.yaml` + `skills/network/bgp-neighbor-down/skill.yaml`
   —— 金标准模板，你产出的一切 Skill 以此为质量基准

## 分工契约

| 模型 | 职责 | 禁区 |
|---|---|---|
| **Fable 5**（架构师/终审） | 顶层设计、schema 演进、金标准、对抗评审、疑难领域 | 不做批量机械工作 |
| **Opus 4.8**（主力工程） | 按 `TODO-opus.md` 执行批量生成与工具开发 | **不得修改** `docs/00-03`、`schema/`；发现设计问题记入 `REVIEW-QUEUE.md` 而非自行修改 |
| 人类（项目发起人） | 方向决策、模型切换、最终审批 | — |

## 工作循环

```
Fable 设计/评审 → 更新 TODO-opus.md → 【人切换到 Opus 4.8】
  → Opus 执行 → 产出 + REVIEW-QUEUE.md → 更新本文件 → 【提示人切换回 Fable】
  → Fable 评审 REVIEW-QUEUE → 合并/打回 → 下一轮
```

规则：
- 每完成一个 TODO 条目即 git commit（小步提交，commit message 带条目编号，如 `[O-3]`）。
- Opus 完成全部条目或遇到阻塞时：更新本文件"当前状态"，然后**在回复末尾明确提醒用户：
  "请切换回 Fable 5 进行评审"**。
- 评审不通过的产出不删除，移入 `attic/` 并在 REVIEW-QUEUE 记录原因（留痕供改进）。

---

## 当前状态（由最后工作的模型更新）

- **更新时间**：2026-07-09（Fable 四轮评审后覆盖）
- **更新者**：Fable 5
- **阶段**：四轮评审完成，**第五轮任务书已发（TODO-opus.md U-1~U-5），交接给 Opus 4.8**
- **四轮评审结论**：
  - **运行时 CLI 验收通过**——变更简报呈现即"踏实感产品化"，安全默认正确；4 个打磨项入 U-1
  - **F-10 已修**：XID 92（可纠正 SBE 率预警）被误归不可纠正硬件类，会对好卡触发 drain+RMA；
    分支与 caution 清单不一致——教训入 docs/07 B9（枚举清单双向核对）
  - **S13 求值冒烟采纳并已实现**（docs/03 §7.6d）：所有 when/assert 入库前空 ctx 实跑求值器，
    拦截 or-bug 类"语法过、求值崩"缺陷；全库 61 Skill 通过
  - F-11 记录：opsaxiom-collect 未实现（F-6 同型第二次出现）→ U-2 + 规范补条
  - 其余 9 个 aicomp 领域判断合格
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第五轮 U-1 开始（CLI 打磨/collect 工具/obs-sec-proc 域/签名）

---

## 历史状态存档（七）

- **更新者**：Opus 4.8（四轮完成，里程碑：运行时 CLI）
- 61 Skill、37 sim_verified、opsaxiom run/diagnose 落地、or-bug 修复
- **第四轮交付**：
  - T-1 **运行时导航档 CLI**（`opsaxiom run`）：逐节点交互、变更简报渲染、写操作只指导不代执行、
    verify 判定、模板渲染、全程审计 jsonl。2 个端到端演示(disk-full 含变更简报/mysql)入 tests
  - T-2 **`opsaxiom diagnose "<症状>"`**：L1 域加权 + 中文 bigram 匹配，6 域 top-1 命中
  - T-3 R-7 渲染契约 `{{output.<scalar>}}` 落地 + FIELD 模板校验 + 恢复标量引用
  - T-4 mysql 5 Skill 版本限定(versions>=8.0) + 5.7 降级 caution + docs/07 B8
  - T-5 **aicomp 域 10 Skill**（引爆点域，XID 码表精确），全部 sim_verified；
    **顺带修了求值器 or 短路 bug**（运行时任何 or 表达式都会崩，校验器无此问题因不求值）
  - 全库 **61 Skill**（host20/k8s10/network11/middleware10/aicomp10），37 sim_verified；
    校验 61/61、pytest 193/193、仿真 43/43 全绿
- **交接给**：**Fable 5 —— 四轮评审**，重点：
  1. **运行时 CLI 的产品体验**：`opsaxiom run` 的导航档 UX 是否符合"贴心 step-by-step 助手"的最初设想？
     变更简报呈现、"只指导不代执行"的边界、审计粒度——请从产品视角审。
  2. **抽查 aicomp 10 Skill 的领域正确性**（我是生成方，且这是引爆点域）：尤其 **XID 码表**
     （13/31/43/45 软件 vs 48/94/95 硬件 ECC vs 79 掉卡 vs 74 NVLink vs 63/64 退休）、
     DBE 禁重试、NCCL 退化 TCP 的判断、木桶效应慢节点定位。
  3. **or 短路 bug 的启示**：这类"校验器测不出、运行时才崩"的求值器 bug，是否该补一条
     "所有 when/assert 在入库前用样例 ctx 实跑一次求值"的校验(区别于纯语法校验)？
- **下一轮候选**：obs/sec/proc 域 Skill；attestation 真实签名；registry(Skills Hub)雏形；
  IM 渠道接入(钉钉/飞书)——留存的生命线；真实靶机执行器扩到 network/k8s；导航档 CLI 打磨(彩色/断点续跑)。

---

## 历史状态存档（六）

- **更新者**：Fable 5（三轮评审）
- 第四轮任务书已发（T-1~T-6，里程碑：运行时 CLI）
- **三轮评审结论**：
  - F-9 由 Fable 修复（disk-full 4 处 df 列序统一 + verify 补 parser），真实模式复跑语义正确，
    重新晋级为 real_roundtrip 证据；教训入 docs/07 B7
  - R-7 采纳：`{{output.<scalar>}}` 约定入 docs/03 §7.6c，实施 T-3
  - middleware 10 Skill 抽查合格（反 skip、noeviction、LFU 前提、分区并行上限等关键判断全对）；
    nit：mysql 8.0 表名缺版本限定 → T-4
  - S12/FIELD 严格度接受现状；`any(A) and any(B)` 同集合误用属静态不可判定，
    B6+派生标量+评审三层防御，残余风险记录为已知边界
  - R-1~R-7、F-1~F-9 全部关闭或已裁决；R-5 余引擎快照部分随运行时实施
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第四轮 T-1 开始。**本轮是从资产到产品的里程碑**：
  导航档运行时 CLI + Skill 匹配 + aicomp 域。

---

## 历史状态存档（五）

- **更新者**：Opus 4.8（三轮完成）
- 51 Skill、27 sim_verified、S12/字段契约/真实执行器/attest 落地
- **第三轮交付**：
  - Q-1 **S12 投影语义静态检测**：拦截 F-8 类"看似对求值错"的裸投影写法（exprlang.check_projection）
  - Q-2 **解析器字段契约**：parser_fields.yaml 声明 40+ 解析器输出；6 个真实健康解析器闭合 R-5 字段；
    FIELD 校验（when/assert 字段须有来源，WARN）
  - Q-3 **真实靶机执行器**：run_sim mode:real 本机跑真实命令+真实解析器+真实分支；证据分级
    context_walk / real_roundtrip；3 诊断升级 real_roundtrip；**首跑即发现 F-9**（金标准 disk-full
    命令列序 vs 解析器不匹配——context_walk 测不出、real 一跑就现形）
  - Q-4 **opsaxiom-attest**：脱敏分桶 attestation 生成 + schema（防精确版本 PII）+ 校验器接入
  - Q-5 **middleware 域 10 Skill**（mysql5/redis3/kafka2），严守 B6 全部过 S12，10 个晋级
  - 全库 **51 Skill**（host20/k8s10/network11/middleware10）；27 sim_verified；
    校验 51/51、pytest 160/160、仿真 32/32 全绿
- **交接给**：**Fable 5 —— 三轮评审**，重点：
  1. **F-9（需你修金标准）**：disk-full 的 locate_mount 命令 `--output=target,pcent,avail` 与
     df-v1 解析器（pcent 末列）不匹配，真实模式落 escalate。一行修复后可补跑升级 real_roundtrip。
  2. **R-7（需定口径）**：检查节点的标量输出（max_query_time 等）在 summary 里无合法模板写法——
     建议 v0.3 给 `{{output.<scalar>}}` 约定，与 Q-2 字段契约对齐。
  3. **抽查 middleware 10 Skill 领域正确性**（我是生成方）：尤其 mysql 复制 1062/1032 不许 skip、
     redis noeviction 拒写语义、kafka "分区数=消费并行上限"。
  4. **S12/FIELD 是否够严**：S12 只拦"裸投影入 and/or"，拦不住 `any(A) and any(B)` 同集合语义误用
     （无法静态判定）——是否接受靠 B6+评审兜底。
- **下一轮候选**：F-9 修复后补跑；R-5/R-7 的引擎契约实施；aicomp(GPU/NCCL)/obs/sec 域 Skill；
  attestation 真实签名；containerlab 网络设备仿真；k8s rollout undo 录制-回放（sim/README 已设计）。

---

## 历史状态存档（四）

- **更新者**：Fable 5（二轮评审）
- 第三轮任务书已发（Q-1~Q-6）
- **二轮评审结论**：
  - R-6 追认关闭（口径入 docs/05）；R-5 方向确认（规范入 docs/03 §7.6b，实施 Q-2）
  - **F-8（最重要）**：投影语义缺陷致 stp-loop/acl-block 在正常环境静默误报——已实测复现并修复
    （改解析器派生标量），规范入 docs/03 §7.6a + docs/07 B6，S12 静态检测列 Q-1
  - network 域其余 8 个 Skill 领域正确性合格（光功率 DDM 阈值、OSPF 状态机、df-bit 等均对）
  - sim_verified 证据分级定稿（context_walk / real_roundtrip，docs/05），17 个晋级维持有效
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第三轮 Q-1 开始，按序执行

---

## 历史状态存档（三）

- **更新者**：Opus 4.8（第二轮完成）
- 第二轮 P-1~P-6 全部完成，41 Skill、17 sim_verified、校验/测试/仿真全绿
- **第二轮交付**：
  - P-1 schema v0.2 落地 + 全部 31 Skill 迁移（params/ask.binds/verify.assert/S11/avg-sum/
    模板文法/S9 升 ERROR/facts 注册表），关闭 R-1/R-3/R-4/F-2/F-4
  - P-2 修 F-3/F-5/F-7 + `docs/07-authoring-rules.md`（飞轮：评审教训→生成规范）
  - P-3 `opsaxiom-deploy`（幂等/可卸载/checksum/可测）
  - P-4 `tools/promote.py` maturity 流水线（重放 disk-full 晋级一致）
  - P-5 16 新仿真场景，晋级 **17 个 sim_verified**（含 agent-deploy 真实部署回滚往返）
  - P-6 network 域 **10 个新 Skill** + 扩语法树（现 network 共 11）
  - 全库 **41 Skill**（host20/k8s10/network11）；校验 41/41、pytest 130/130、仿真 19/19 全绿
- **交接给**：**Fable 5 —— 二轮评审**，重点：
  1. **追认 R-6**（S8 对纯诊断 Skill 的精化——我已实现，需你在 docs 定口径）
  2. **R-5**（verify.assert 引用了未实现的解析器健康字段 service_active/mount_rw 等——解析器契约）
  3. **抽查 P-6 network 10 个 Skill 的领域正确性**（我是生成方；尤其光功率阈值、STP/OSPF 状态判断、
     MTU 黑洞 df-bit 用法、acl-block 是否真守住"只诊断不改"边界 D1）
  4. **P-5 的仿真诚实性**：诊断类场景是"给定结构化上下文走树"（非真实靶机），
     只有 quarantine/deploy 是真实回滚往返——sim_verified 的证据强度是否达到你对该徽章的预期？
- **下一轮候选**：真实靶机执行器(替换 sim 模拟上下文)；k8s rollout undo 录制-回放(sim/README 已设计)；
  解析器补齐(R-5 健康字段 + network ntc 模板)；registry/attestation CLI(docs/05)；
  containerlab 网络设备仿真；middleware/aicomp/obs/sec 域 Skill。

---

## 历史状态存档（二）

- **更新者**：Fable 5（第一轮评审）
- 第二轮任务书已发（P-1~P-6）
- **第一轮评审结论**：
  - R-1~R-4 全部裁决（采纳/采纳变体），规范细节在 docs/03 §7（v0.2 决议）
  - 新发现 F-1~F-7 记入 REVIEW-QUEUE：F-1(raid 写死 md0)已由 Fable 直接修复，
    F-2 裁决为新规则 S11，其余进 P-2/P-3
  - 高危 Skill 抽查合格（关键 caution 与命令用法均正确），无打回
  - disk-full 依据仿真证据晋级 sim_verified（Fable 代行流水线，正式工具见 P-4）
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第二轮 P-1 开始，按序执行

---

## 历史状态存档

- **更新时间**：2026-07-09
- **更新者**：Opus 4.8
- **阶段**：首轮批量执行（TODO-opus.md O-1~O-7）**全部完成**，等待 Fable 对抗评审
- **本轮交付**：
  - O-1 分类 L3 全量清单（docs/04 §5，8 域）+ 归属存疑记 docs/_inbox.md
  - O-2 校验器 tools/validate.py：结构 + 语义 S1–S10，受限表达式 fail-closed(tools/exprlang.py)
  - O-3 host 域 20 个 Skill（disk-full 金标准 + 19 新增）
  - O-4 k8s 域 10 个 Skill（rollback/rollout 用 transaction 型回滚）
  - O-5 解析器库(tools/parsers) + 命令语法树(tools/syntax)，S6 升为真实校验，拦截跨平台 CLI 幻觉
  - O-6 仿真环境(sim/)：求值器 + 执行器 + opsaxiom-quarantine，disk-full 三路径全过含真实回滚往返
  - 校验器全量 **31/31 过**，pytest **90/90 过**
- **交接给**：**Fable 5 —— 请进行对抗评审**，重点：
  1. **REVIEW-QUEUE.md 的 R-1~R-4**（都需要 schema v0.2 决策）：
     - R-1 S9 无声明位（建议加 metadata.params + ask.binds）——**最该先定**，影响所有 Skill
     - R-3 表达式缺 avg/sum（我用 count(...)>=k 绕过了，但建议补）
     - R-2 verify.expect 自由文本、R-4 模板变量下标语法
  2. **抽查 Skill 的领域正确性**（我是生成方，命令/阈值/cautions 需专家复核）——
     建议优先审带 action 的高危 Skill：fs-readonly(critical/human_only)、k8s/rollback、clock-drift、agent-deploy
  3. **金标准 maturity**：disk-full 已通过仿真+回滚往返，具备 sim_verified 条件，但我未擅自改
     maturity（遵守"由流水线写入"约定）——请确认是否搭建 maturity 流水线或授权手动晋级
- **已消化的原未决问题**：
  - 项目定名 OpsAxiom ✓；工具名统一 opsaxiom-* ✓
  - 受限表达式：已实现 tokenizer+parser（校验）+evaluate（求值），保守子集，见 tools/exprlang.py
  - opsaxiom-quarantine 已实现且测试通过（move/restore/list/purge）
- **下一轮候选（未开工）**：network 域 Skill 包 + containerlab 真实设备仿真；host/k8s 剩余 L3 叶子；
  registry/attestation CLI（docs/05 的 `opsaxiom attest`）；真实靶机执行器（替换 sim 的模拟上下文）。
