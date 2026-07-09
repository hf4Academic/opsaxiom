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

- 设计阶段完成（Fable 5）：黄金准则、架构、Schema、分类、认证体系。
- 首轮批量执行完成（Opus 4.8）：31 个 Skill（host 20 / k8s 10 / network 1）、校验器、
  解析器库、命令语法树、仿真执行器 + 隔离工具。校验 31/31、pytest 90/90 全绿。
- 下一步：Fable 5 对抗评审（见 HANDOFF.md 与 REVIEW-QUEUE.md）。

## 开发者快速上手

```bash
pip install -r tools/requirements.txt
python3 tools/validate.py skills/            # 校验全部 Skill（结构 + 语义 S1–S10 + 命令语法树）
python3 -m pytest tools -q                   # 运行全部测试
python3 sim/run_sim.py sim/scenarios/disk-full-inode-exhaustion.yaml   # 跑一条仿真场景
```

> 命名说明：项目名 **OpsAxiom**（axiom = 公理，呼应"黄金准则"与"Schema 是法律"的设计哲学）。
> 仓库内部标识符（`opsagent-*` CLI 工具名、schema $id）在 O-6 实现工具时统一改为 `opsaxiom-*`。

## License

Apache-2.0（拟）
