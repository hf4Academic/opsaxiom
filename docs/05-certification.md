# 社区验证与认证体系（Certification v0.1）

> 设计目标：把"人在真实环境里验证过"变成可累积、可信任、可普惠的公共资产（R12），
> 同时防刷、防腐烂。认证的对象是 **Skill 的特定版本**，不是 Skill 本身。

## 1. 成熟度阶梯

| 级别 | 徽章 | 晋级条件 | 运行时权限 |
|---|---|---|---|
| `draft` | ⚪ 生成 | 通过 schema + 语义校验（S1–S10） | 仅导航档，且每屏带"未验证"警示 |
| `sim_verified` | 🔵 仿真 | 全部 tests 在 CI 仿真环境通过，含回滚断言 | 导航 + 协驾档 |
| `field_verified` | 🟢 实地 | ≥ 3 份**独立**有效 attestation，且无未决否决票 | 全部三档（自驾档高危仍需审批） |
| `certified` | 🟡 认证 | field_verified + 领域评审人签署 review + 累计 ≥ 10 份 attestation | 全部三档；进入官方推荐列表 |

降级规则（自动，由流水线执行）：
- 滚动 90 天内 👎 比例 > 30% 或收到任一"回滚失败"报告 → 立即降至 `draft` 并冻结自驾档；
- `expires_review` 过期未复审 → 降一级；
- Skill MAJOR 版本变更 → maturity 重置为 `draft`（旧版本的 attestation 不继承，但保留可查）。

## 2. Attestation（实地验证记录）—— 核心数据结构

用户在真实环境走完一个 Skill（任意档位）后，Agent 发起两段式反馈：

1. **单比特**（必答一次点击）：解决了吗 👍/👎 —— 零摩擦，人人会答。
2. **结构化 attestation**（自愿，30 秒表单）：这才是认证货币。

```yaml
# skills/<domain>/<slug>/attestations/2026-07-08-a1b2c3.yaml
skill: host.storage.disk-full
skill_version: 0.3.0
outcome: resolved            # resolved | partial | failed | made_worse
mode: navigator              # navigator | copilot | autopilot
env_fingerprint:             # 脱敏的环境画像——只有分桶信息，无任何标识性数据
  os: {family: rhel, version_bucket: "8.x"}
  scale_bucket: "10-100 hosts"
deviations: []               # 与决策树的偏离步骤（有偏离 = 决策树改进线索）
rollback_exercised: false    # 是否实际触发过回滚（true 的权重显著更高）
attestor: gh:someuser        # 签名者（GitHub 身份 / 企业 SSO 身份）
signature: <detached-sig>    # 对本文件内容的签名，工具链自动生成
```

提交通道：`opsagent attest` 命令自动生成文件并发 PR（或经 registry API）。
**attestation 目录 append-only**：只增不改不删，形成可审计的历史。

## 3. 独立性与防刷

"≥ 3 份独立 attestation"中的**独立**定义为：
- 不同 attestor，且
- env_fingerprint 不同分桶，且
- attestor 之间无同组织标记（企业域名 hash 分桶）。

防刷机制：
- attestor 信誉分：新账号的 attestation 权重 0.3，随历史记录被交叉印证而上升；
  被发现虚假记录 → 信誉清零并回溯削权其全部历史记录。
- 认证流水线核算 maturity 时只认加权和，权重规则开源、可复算（S10：不接受手工声明）。
- 否决票（`made_worse` / 回滚失败）任何人可投，但需附结构化细节，触发强制人工复审。

## 4. 人力如何被 involve、成果如何普惠（激励设计）

三种角色，三种持久产出：

| 角色 | 做什么 | 持久产出 | 激励 |
|---|---|---|---|
| **验证者**（任何用户） | 真实环境跑 Skill 后提交 attestation | attestation 文件 | Skill 页面署名"verified by"；信誉分；验证数排行榜 |
| **评审人**（领域专家，申请+历史记录准入） | 审 `field_verified → certified` 的晋级；审否决票 | review 记录（签名文件） | Skill 页面署名"certified by"；领域评审人头衔（网络/智算/K8s 各设组） |
| **贡献者** | 写/改 Skill、解析器、测试 | git 提交历史 | 常规开源署名 + 其 Skill 的 attestation 数即影响力指标 |

关键设计决策：
- **所有三类产出都是仓库里的签名文件**，不是平台数据库里的一行记录——项目被 fork、
  registry 迁移、公司倒闭，社区的验证劳动都不丢失（R12）。
- 偏离记录（deviations）是隐藏的金矿：某步骤被反复偏离 = 决策树该改了，
  流水线自动聚合偏离并生成改进 issue。
- 企业内网用户（无法外发数据）可运行**私有 registry**：attestation 留在内网，
  但格式相同——企业内部照样形成自己的认证层，与公共层叠加使用。

## 5. 与运行时的联动

- 运行时加载 Skill 时按 maturity 决定可用档位（§1 表）；
- 呈现任何建议时附带徽章与数字（"🟢 已被 17 个环境验证，最近验证 3 天前"）——
  这行字本身就是产品的信任界面（R8）；
- `draft` Skill 的每条指导下方附"这条建议来自模型生成，尚未经实地验证"。

## 6. 冷启动策略

发布 v1 时没有社区，先自建三层：
1. 官方 Skill 全部过仿真 → 带 🔵 出厂；
2. 项目方与种子用户（内测企业）在真实环境跑出首批 🟢；
3. 邀请 5–10 位有公开声誉的运维专家做首批评审人，产出首批 🟡。
发布时页面上必须已经存在三种徽章的真实样本，让新用户第一眼就理解这套体系。
