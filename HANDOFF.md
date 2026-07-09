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
