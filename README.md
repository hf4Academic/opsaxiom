# OpsAxiom

> 一个面向运维人员的开源智能体：把运维专家的判断编译成**可验证、可回滚、可认证**的
> Skill 资产，让任何模型——包括跑在你内网的本地小模型——都能安全地使用它。

## 一句话定位

别人是"把大模型接到运维工具上"；我们是把专家经验做成经过仿真与实地双重验证的决策树，
配上强制回滚、变更简报和社区认证体系。**可回滚是本项目的第一准则。**

## 与现有工具的区别

- **HolmesGPT / K8sGPT**：只读诊断、K8s 为主 → 我们覆盖主机/网络设备/智算等全栈，且能安全执行变更
- **通用 Agent**：运行时现场推理，换个环境就翻车 → 我们的步骤从你的环境事实里长出来，
  每条命令过语法树校验，每个写操作先物化回滚方案
- **传统 runbook**：静态文档 → 我们是逐步验证的交互式执行，且带社区认证徽章（⚪🔵🟢🟡）

## 三档交互（信任阶梯）

1. **导航**：Agent 出方案+变更简报，人执行——零凭据即可用
2. **协驾**：Agent 执行只读命令与 dry-run
3. **自驾**：Agent 执行变更，高危动作过审批门

## 仓库导览

| 路径 | 内容 |
|---|---|
| `HANDOFF.md` | **模型交接协议与当前状态（接手先读这个）** |
| `docs/00-golden-rules.md` | 黄金准则（宪法，12 条） |
| `docs/01-architecture.md` | 核心架构与差异化逻辑层 |
| `docs/02-rollback-design.md` | 可回滚保证机制 |
| `docs/03-skill-schema.md` + `schema/` | Skill Schema v0.1（法律层） |
| `docs/04-taxonomy.md` | 运维知识地图 / 故障分类树 |
| `docs/05-certification.md` | 社区验证与认证体系 |
| `skills/` | Skill 库（含 2 个金标准样例） |
| `TODO-opus.md` | 当前执行批次的任务书 |

## 项目状态

- **61 个 Skill**（host 20 / k8s 10 / network 11 / middleware 10 / aicomp 10），37 个 `sim_verified`。
- 完整工具链：校验器（结构 + 语义 S1–S12 + 投影语义 + 字段契约 + 命令语法树）、
  解析器库、仿真执行器（context_walk + 真实靶机）、maturity 流水线、attestation CLI。
- **运行时 CLI 已落地（导航档 MVP）**：`opsaxiom diagnose "<症状>"` 匹配 Skill，
  `opsaxiom run <id>` 逐步指导排查/变更（Agent 只出方案与变更简报，写操作由你亲自执行）。
- 经四轮"Opus 生成 / Fable 对抗评审"迭代，累计沉淀 9 条生成规范教训（docs/07）。

## 试一下运行时（导航档）

```bash
# 按症状找 Skill
python3 tools/bin/opsaxiom diagnose "磁盘满了 No space left"
# 走一遍排查（脚本驱动的演示；去掉 --answers 即为真人交互）
python3 tools/bin/opsaxiom run host.storage.capacity.disk-full \
  --answers demos/disk-full-guided.answers.yaml
```

## 开发者快速上手

```bash
pip install -r tools/requirements.txt
python3 tools/validate.py skills/            # 校验全部 Skill（结构 + 语义 S1–S12 + 命令语法树）
python3 -m pytest tools -q                   # 运行全部测试
python3 sim/run_sim.py sim/scenarios/disk-full-inode-exhaustion.yaml   # 跑一条仿真场景
```

> 命名说明：项目名 **OpsAxiom**（axiom = 公理，呼应"黄金准则"与"Schema 是法律"的设计哲学）。
> 仓库内部标识符（`opsagent-*` CLI 工具名、schema $id）在 O-6 实现工具时统一改为 `opsaxiom-*`。

## License

Apache-2.0（拟）
