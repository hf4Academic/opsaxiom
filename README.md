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
| `docs/09-interaction-v2.md` | 交互模型 v2：取证式诊断（陈述→取证→卷宗→处置→复盘） |
| `tools/pi/opsaxiom.ts` | pi 智能入口扩展（欢迎界面 / `/connect` / axiom_* 工具 / 工具面收窄） |
| `Dockerfile` + `docker-compose.yml` | 多阶段镜像（core / llm / full 三档重量） |
| `TODO-opus.md` | 当前执行批次的任务书 |

## 项目状态

- **73 个 Skill**（host 20 / k8s 10 / network 11 / middleware 10 / aicomp 10 / obs 5 / sec 4 / proc 3），
  49 个 `sim_verified`。
- 完整工具链：校验器（结构 + 语义 S1–S13 + 投影语义 + 字段契约 + 命令语法树）、
  解析器库、仿真执行器（context_walk + 真实靶机，含 kubectl 只读白名单）、
  **maturity 流水线（sim_verified → field_verified，≥3 份独立签名 attestation）**、
  **Ed25519 签名的 attestation + keyring 治理**。
- **告警入口（增强渠道）**：`opsaxiom diagnose --json` + `opsaxiom-webhook` 收 Alertmanager
  告警 → 匹配 Skill → 推钉钉/飞书卡片（只荐不代执行）。
- **运行时 CLI 已落地（导航档 MVP）**：`opsaxiom diagnose "<症状>"` 匹配 Skill，
  `opsaxiom run <id>` 逐步指导排查/变更（Agent 只出方案与变更简报，写操作由你亲自执行），
  支持 `--resume` 断点续跑、变更节点 skip/升级/退出多选。
- **人侧飞轮已打通**（docs/08、docs/10）：一键部署（`install.sh`/docker/离线包）+ `doctor` 自检；
  经验捕获三通道（`skill from-session`/`record`/`skill new`）把日常排查变 Skill 草稿；
  排查终点一键认证（30 秒签名沉淀）；**Skills Hub**（`hub pull` 三道安全门 / `hub push` / 静态站生成器）。
- **默认交互入口是 Terminal REPL，交互模型 v2（取证式诊断）**：裸敲 `opsaxiom` 进交互态，
  说一遍问题 → 并行多假设、一轮批量取证（只读命令自动跑/远端一次粘贴）→ 诊断卷宗
  （证实/排除/证据不足，每条带证据引用）→ 处置审批 → 复盘导出。像急诊医生，不像客服问卷
  （设计见 docs/09）。**可选接模型**只做理解/叙事/建议，永不出命令、不判分支：
  内置千问 0.5B（`opsaxiom model pull` 本机离线跑，开箱备用）/ Ollama / OpenAI 兼容
  远程 API / **Pi Agent Harness 多 provider 网关**，`opsaxiom model` 一条命令切换，
  首启有向导；任一后端不可用自动降级，绝不阻塞排查。
- 经七轮"Opus 生成 / Fable 对抗评审"迭代，累计沉淀 11+ 条生成规范教训（docs/07）。

## 开箱即用（实测流程）

**1) 一键安装**（装依赖、软链命令、初始化密钥、自动体检）：

```bash
git clone <本仓库> && cd OpsAxiom
./install.sh
export PATH="$HOME/.local/bin:$PATH"   # 若安装末尾提示 PATH，加这行（可写进 ~/.bashrc）
```

装完自动跑 `opsaxiom doctor`：🟢 全绿即可用；🟡 只是可选连接器缺失（如本机没装
kubectl，只影响 k8s 域的真实执行，**导航档不受影响**）。

**2) 用：敲一个词，然后说人话**

```bash
$ opsaxiom
OpsAxiom v0.1 · 73 个 Skill（49 已验证）· 输入你遇到的问题，或 help 看用法
axiom> 磁盘满了但 df 显示还有空间 mount=/data
  假设 3 个（按相关度）：inode 耗尽 / 已删除未释放 / …
  本机可自动执行 5 条只读取证命令（均出自已验证 Skill）。授权？[y/N]: y
  ▶ 取证中（本机只读自动执行）… 完成
  ── 诊断卷宗 ──────────────────────────────
  ✔ 已证实  磁盘空间耗尽  证据: df -i → rows[0].ipcent = 99  → 待处置：移入隔离区
  ✘ 已排除  已删除未释放  证据: lsof +L1 → 无残留句柄
  → 处置：run host.storage.capacity.disk-full（进入导航档执行变更）
axiom> gpu 掉卡 xid 79        ← 换个域接着问
axiom> report                 ← 把当前卷宗导出为故障报告（贴工单/转人工）
axiom> quit
```

规矩：**写操作永远由你亲手执行**，它只给方案、变更简报和回滚命令；取证只跑只读命令；
判读全由机器按解析器字段算，证据不足就明说还差什么。远端设备则给你一整块命令一次贴回。
中途 Ctrl-C 暂停（进度已存），`resume` 续跑；输候选序号可回到老式逐步排查（兜底）。

**3) 脚本/自动化用子命令**：

```bash
opsaxiom doctor                                   # 环境自检（排障第一命令）
opsaxiom diagnose "kafka 积压" --json             # 结构化候选（给自动化/webhook 用）
opsaxiom run host.storage.capacity.disk-full \
  --answers demos/disk-full-guided.answers.yaml   # 脚本驱动演示；去掉 --answers 即真人交互

# 告警→IM 卡片（--dry-run 只打印不出站）：
echo '{"alerts":[{"labels":{"alertname":"GPU 掉卡 XID 79"}}]}' | opsaxiom-webhook --dry-run
```

## pi 智能入口（可选升级层）

装了 [Pi Agent Harness](https://pi.dev)（node≥22.19）后，裸敲 `opsaxiom` 会**自动进 pi 智能入口**；
探测不到 node/pi 就无感回落到上面的 Terminal REPL（气隙/无 node 环境一字不变，导航档零依赖承诺不破）。
`opsaxiom classic` 可强制老 REPL。

pi 入口是"模型驱动的外壳，OpsAxiom 是法律"：模型能调的只有 `axiom_diagnose`/`axiom_incident`/
`axiom_report` 三个工具，工具内部全是确定性引擎——**模型永远拿不到出命令、判分支的权力**
（R7/R9/R10 在工具边界上成立）；写操作仍走 `opsaxiom run` 的审批门。

```
   ∩      ∩
 (  -    -  )      ◆ OpsAxiom × pi          ← 启动欢迎：卡皮巴拉
 (    ᴥ     )
axiom 里可用的命令：
  /connect   接一个模型：选服务商 → 输 API Key → 当场选模型（连接本机 0600 保存，重启恢复）
             预置 DeepSeek/Claude/OpenAI/Gemini/OpenRouter/阿里百炼/Kimi，
             或「✎ 自定义」自己填 Base URL / API Key / Model ID（vLLM/内网网关都行）
  /model     在已接入的模型间切换
  /axiom     看 Skill 库与模型后端状态
```

一键装 pi（用国内 npm 镜像）：

```bash
export PATH="$HOME/.local/node22/bin:$PATH"     # 若用便携版 node22
npm install --prefix ~/.local/pi-agent @earendil-works/pi-coding-agent
opsaxiom            # 裸敲即自动进 pi 入口（首次先 /connect 接你的模型）
```

三种模型接法，都在 `/connect` 里：**远程 API**（自己输 Key，最省心）/ **本机 Ollama** /
**内置千问 0.5B**（`opsaxiom model pull` 下载后 `opsaxiom model serve` 起服务，离线备用）。

## 开发者快速上手

```bash
pip install -r tools/requirements.txt
python3 tools/validate.py skills/            # 校验全部 Skill（结构 + 语义 S1–S13 + 命令语法树）
python3 -m pytest tools -q                   # 运行全部测试
python3 sim/run_sim.py sim/scenarios/disk-full-inode-exhaustion.yaml   # 跑一条仿真场景
```

> 命名说明：项目名 **OpsAxiom**（axiom = 公理，呼应"黄金准则"与"Schema 是法律"的设计哲学）。
> 仓库内部标识符（`opsagent-*` CLI 工具名、schema $id）在 O-6 实现工具时统一改为 `opsaxiom-*`。

## License

Apache-2.0（拟）
