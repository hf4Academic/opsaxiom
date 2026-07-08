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

- **更新时间**：2026-07-08
- **更新者**：Fable 5
- **阶段**：设计阶段完成，进入首轮批量执行
- **已完成**：
  - 黄金准则 12 条（docs/00）
  - 核心架构与差异化逻辑（docs/01）
  - 可回滚机制设计（docs/02）
  - Skill Schema v0.1：文档（docs/03）+ JSON Schema（schema/skill.schema.json）
  - 分类体系 L1/L2（docs/04，L3 待 Opus 扩展）
  - 认证体系设计（docs/05）
  - 金标准 Skill ×2（host/disk-full、network/bgp-neighbor-down）
  - Opus 任务书（TODO-opus.md，7 个条目）
- **交接给**：Opus 4.8 —— 从 `TODO-opus.md` 的 O-1 开始，按序执行
- **未决问题**（Opus 无需处理，留给 Fable/人）：
  - ~~项目命名未定~~ → 已定名 **OpsAxiom**（2026-07-08）；内部 `opsagent-*` 标识符在 O-6 统一更名 `opsaxiom-*`
  - 受限表达式语言的正式文法（当前只有 docs/03 §5 的描述性定义，O-2 会先实现一个保守子集）
  - `opsagent-quarantine` / `opsagent-restore` 工具本身尚不存在（O-6，实现时用 `opsaxiom-` 前缀）
