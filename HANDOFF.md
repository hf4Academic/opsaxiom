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
- **本文件里所有"已具备/已实现"表述，写入前必须实测过**（F-15/docs07 T-2）：
  虚报比缺功能严重，下一个接手者会基于假前提做设计。

---

## 当前状态（由最后工作的模型更新）

- **更新时间**：2026-07-12（Opus 第十轮 Z-1~Z-6 完成）
- **更新者**：Opus 4.8
- **阶段**：**第十轮（交互模型 v2）全部完成，交接 Fable 5 十轮评审**
- **第十轮交付（docs/09 设计 → 实现，零 Skill 迁移、schema 不动、R1–R12 不动）**：
  - **Z-1 环境事实库**（tools/facts.py）：fact=key/value/source_cmd/target/ts/ttl/parser/field；
    key=目标+归一化命令+字段；解析器输出自动入库（BUNDLE 供 check 复用 + 标量/首行字段供
    卷宗证据链）；故障态 TTL 300s；target 隔离；save/load 随审计归档且过期即弃。兑现 docs/01 §3。
  - **Z-2 检查前沿提取**（tools/evidence.py）：静态分析树，从 entry 可达+命令可渲染的
    check/discovery 入前沿；多假设合并、按事实键去重、波次分组。"纳入前沿"只看可达+可渲染
    （网络设备 show 也纳入），"是否自动执行"另判（auto=本机 and _is_readonly）——F-16 白名单不松。
  - **Z-3 批量取证执行**（tools/sweep.py）：本机协驾 execute_auto 自动跑（执行时二次校验只读
    + T-3 param 注入防护）；导航档单粘贴块（nonce 分隔符）+ collect/ingest 回灌；trust.yaml
    逐目标一次性授权。回合数 O(节点)→O(1 粘贴)。**三条对抗纪律带测试**（伪造分隔符判数据/
    param 注入拒执行/白名单外二次拦截）。
  - **Z-4 incident 会话与诊断卷宗**（tools/incident.py + REPL v2）：incident 取代裸 session；
    假设在事实上**干跑**（判读全走 exprlang，一行不进 LLM/启发式），三态 confirmed/refuted/
    insufficient；卷宗三栏带证据引用与徽章；escalate 出移交卷宗；done 导出故障报告 md。
    两条端到端链路入 tests（disk-full 本机全自动取证用真实解析器、bgp 导航一次粘贴）。
  - **Z-5 LLM 适配层**（tools/llm.py，可选可降级）：model.yaml（ollama/openai-compatible，
    urllib 不加依赖）；三调用点 intake/叙事/escalate 助理，各有静默降级，**无模型全功能可用**。
    铁律由代码结构强制（不出命令、不判分支、输出过白名单、送模型前 redact、param 值过 shell 校验）。
    脱敏收敛到 redact.py 单一来源（webhook 改导入）。**对抗测试**（注入仅展示零影响/越权编造 id
    丢弃/危险 param 净化）。
  - **Z-6 收尾**：docs/10 第二章改 v2 主线、README 交互示例更新、docs/model.yaml.example。
- **全库现状**：73 Skill / 49 sim_verified、**323 pytest 全绿 + 3 skipped(无 kubectl)**、
  73 校验全绿、sim 74 全绿。新增 6 个运行时模块 + 5 个测试文件（新增约 60+ 测试）。
- **需 Fable 十轮评审的重点**：
  1. **卷宗 UX 与语义**：三栏（证实/排除/证据不足）划分是否符合直觉；到达 ask/action 判
     "诊断确立(confirmed)+待处置"是否合理；证据引用目前列消费过命令的全部字段（偏多），
     是否该只留驱动分支的判据字段（我记为可优化点，未做——需要 exprlang 引用抽取）。
  2. **干跑判读正确性**：干跑复用 exprlang 与 sim 同源，但缺 parser 的 check 节点
     （如 inode_exhaustion 的 find、check_deleted_open 的 lsof）在真实取证下 rows 为空会走
     otherwise——这类节点在事实驱动流里判读偏保守，是否需要补解析器（Q-2 字段契约延伸）。
  3. **对抗用例完备性**：docs/09 §6 六条，Z-3/Z-5 覆盖了分隔符伪造/param 注入/白名单/
     越权 id/注入零影响；§6.5 事实库投毒仅靠"事实带 source_cmd+证据链"软防，是否够。
  4. **降级链诚实性**：无模型时是否真的全功能（intake→bigram、叙事→原样、escalate→None/索引）。
  5. **排期**：原第九轮 Y（发布准备）现为第十一轮，是否按此推进。
- **M 轮追加（发起人直接指示，2026-07-12）：模型后端扩展**
  - **builtin 内置小模型**：千问 Qwen2.5-0.5B-Instruct GGUF（q4_k_m 469MB，ModelScope
    直连），llama-cpp-python 本机推理——开箱即用的离线备用底座；intake few-shot 化。
  - **`opsaxiom model` CLI**：show/use/test/pull 四动作 + REPL 首启一次性向导；
    四后端 builtin/ollama/remote(openai-compatible)/pi 一键切换，健康探测诚实报缺口。
  - **pi 后端**：tools/pi_bridge.mjs 经 @earendil-works/pi-ai 统一网关调多 provider；
    本机 node18 < 22.19 探测即报、照常降级（发起人上传 pi-main.zip，深度整合留后续轮）。
  - **新防线（真机实测出的）**：intake 已知键形状校验 _PARAM_SHAPE——0.5B 实测会抽出
    mount='/目录磁盘满了' 脏值并静默毒化卷宗（disk-full 被误排除），形状不合即丢，
    宁缺勿错。此案例入 test_llm 对抗用例。
  - 真机验证全过：model test 通、三句自然语言实体抽取正确、NL→取证→卷宗全链路真跑。
  - 全库现状更新：**334 pytest 全绿 + 3 skipped**、73 校验全绿。
- **M 轮评审补充重点**：
  6. 0.5B 的 intake 只有 few-shot+形状校验兜底，narrate/suggest 两调用点对 0.5B 是否
     该默认关（质量存疑）——是否加 per-callsite 开关。
  7. _PARAM_SHAPE 是运行时侧新白名单，是否该与 metadata.params 声明对齐（schema 里
     params 有 source 字段，可加 shape/pattern 声明成为单一事实来源）。
  8. pi 深度整合（把 OpsAxiom 决策树暴露为 pi 的工具/技能）是否立项下一轮。
- **N 轮追加（发起人指示：pi 深度整合 + Docker，2026-07-12）**
  - **pi 智能入口**（tools/pi/opsaxiom.ts）：裸敲 opsaxiom 探测 node≥22.19+pi→自动进 pi，
    否则无感回落老 REPL（R3 零依赖承诺不破）；pi 是外壳、OpsAxiom 是法律——模型只能调
    axiom_diagnose/incident/report 三工具（内部全确定性引擎），setActiveTools 砍写工具与
    裸 shell、before_agent_start 注入运维守则。欢迎界面吉祥物（发起人钦定卡皮巴拉）。
  - **incident JSON API**（tools/incident_cli.py）：opsaxiom incident --json 全链路，
    本机取证有授权门（needs_grant→--grant），远端只出粘贴块计划不执行。pi 工具的后端。
  - **/connect 接模型**：TUI 内选服务商→输 Key→当场选模型，预置 DeepSeek/Claude/OpenAI/
    Gemini/OpenRouter/百炼/Kimi + 自定义(自填 URL/Key/Model)；连接 0600 落盘重启恢复。
  - **model serve + llm_proxy**：内置千问起 OpenAI 兼容服务；垫片解 3 个真机实锤兼容问题
    （content parts 数组→字符串、max_completion_tokens 字段名、HTTP/1.1 chunked SSE）。
  - **Docker**：多阶段 core/llm/full 三档；full 入口先起模型服务并等就绪（解 pi 连模型竞态）。
  - **两个真机实锤修复**：① registerProvider 部分覆盖抹掉内置 provider 的 baseUrl→
    Connection error → 内置服务商改 env 注入 Key；② 千问 GGUF 服务与 pi-ai 的 OpenAI
    兼容差异（见 llm_proxy）。
  - 全库现状更新：**348 pytest 全绿 + 3 skipped**、73 校验全绿。
- **N 轮评审补充重点**：
  9. pi 入口的"工具面收窄"（砍 bash/写工具、只留 axiom_*+只读）是否够严——模型仍能
     调 read/grep/find/ls，是否有信息外泄/绕过取证边界的风险。
  10. **本地 0.5B 驱动 pi 工具调用未端到端验证**（发起人本地自测；容器内疑似 OOM，
      服务常驻~1GB+node+python 超内存）——0.5B 的 tool-calling 能力偏弱是已知风险，
      DeepSeek 等远程模型全链路已通（含系统守则遵循）。建议默认引导用远程/中等模型。
  11. Docker 镜像未实构建（本环境无 docker），仅静态校验+各部件单独真机验证。
- **交接给**：**Fable 5 —— 十轮评审（含 M/N 追加）**

---

## 历史状态存档（十七）

- **更新者**：Fable 5（交互重设计）
- **阶段**：发起人裁决触发交互模型 v2 重设计，第十轮任务书已发（Z-1~Z-6）
- Fable 设计产出 docs/09-interaction-v2.md（问答走树 → 取证式诊断）；可行性实测
  （check 前沿中位数 2、ask 仅 6、action 仅 9）；硬约束零 Skill 迁移/schema 不动/R1–R12 不动；
  排期裁决 Z 优先于 Y（发布准备顺延十一轮）。交接 Opus 从 Z-1 开始。

---

## 历史状态存档（十六）

- **更新者**：Fable 5（八轮评审后）
- **阶段**：八轮评审完成，第九轮任务书已发（Y-1~Y-4：开源发布准备）
- **八轮评审结论**：
  - X-1~X-5 验收通过；两处诚实性自纠获肯定（run_real 连接器键 / F-15 兑现）
  - **F-16 已修（严重）**：kubectl 白名单被 shell 注入穿透（`; rm -rf /`、`$()`、反引号）
    ——只读 kubectl 不需要任何 shell 元字符，出现即拒；回归测试已补
  - **F-17 已修（R11 违规）**：webhook 卡片原样回显告警 description，凭据会推到 IM
    ——匹配文本(全文,本地)与展示文本(结构化+脱敏)分离；回归测试已补
  - field 独立性判定通过（双维去重合 docs/05 §3）
  - **新纪律**：凡白名单/脱敏/验签交付，任务书强制"对抗用例"小节（F-16/F-17 同根：
    测试只测了正例与已知反例，没测攻击者怎么绕）
- **第九轮**：发布工程（LICENSE/CONTRIBUTING/CI）+ registry 试点 + certified 阶梯落地
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第九轮 Y-1 开始

---

## 历史状态存档（十五）

- **更新者**：Opus 4.8（八轮完成：告警入口/k8s只读/keyring/field晋级）
- **第八轮交付**：
  - **X-1 告警入口 B**：`diagnose --json`（兑现 F-15）+ `opsaxiom-webhook`（收 Alertmanager
    告警→diagnose→钉钉/飞书卡片，只荐不代执行，--dry-run 可测）
  - **X-2 k8s 只读真实执行**：kubectl 子命令级白名单（get/describe/logs/top 放行，
    apply/delete/exec/scale 等拒）；run_real 命令提取从只认 linux 键→任一连接器键（诚实性）；
    3 个 k8s real 场景 requires:[kubectl] 无集群跳过
  - **X-3 keyring 治理**（关 R-9）：`hub keyring list/add/remove/export`；签核流程入 docs/08 §3.3a；
    add 后 pull 验签 TOFU→可信（端到端验证）
  - **X-4 field_verified 晋级**：`promote field`——≥3 份独立且验签有效 attestation→🟢；
    认证阶梯 🔵→🟢 首次可踩上
  - **X-5**：docs/07 T 系列（T-1 标识符单一事实来源/T-2 已具备必须实测）；交接规则补条
- **全库现状**：73 Skill / 49 sim_verified、**277 pytest 全绿 + 3 skipped(无 kubectl)**、
  73 校验 / 67 仿真 全绿。
- **需 Fable 八轮评审的重点**：
  1. webhook 卡片的产品形态（钉钉/飞书两家格式、只荐不代执行边界、R11 不含凭据）
  2. kubectl 只读白名单的完备性（exec 已拒；有无遗漏的写动词？token 判定够不够严）
  3. field_verified 独立性判定（不同 attestor 且不同 env 分桶）是否符合 docs/05 §3 本意
  4. 下一步方向：真实 registry 试点（keyring 签核跑一遍）、network 域真实执行器、
     certified 认证阶梯（领域评审人签署，docs/05）
- **交接给**：**Fable 5 —— 八轮评审**

---

## 历史状态存档（十四）

- **更新者**：Fable 5（七轮评审）
- 修 F-14(resume sid)、F-15(诚实性)、REPL 验收通过、第八轮任务书 X-1~X-5
- **七轮评审结论**：
  - **W-1~W-4 验收通过，REPL 产品体验合格**（pty 真 TTY 实测：症状匹配/info/quit 顺畅，
    无 TTY 降级正确，防镀金边界守住）
  - **F-14 已修**：REPL resume 用 skill_id 重派生 sid 丢真实会话——改为传状态文件真实 sid；
    教训"标识符单一事实来源"（X-5 落 docs/07 T-1）
  - **F-15（诚实性）**：HANDOFF 声称 diagnose --json 已具备，实测不存在——虚报比缺功能严重；
    兑现入 X-1，交接规则补"已具备必须实测"（X-5）
- **第八轮**：告警入口 B（webhook→diagnose→钉钉/飞书卡片）+ k8s 只读真实执行 +
  keyring 治理（关 R-9）+ field_verified 晋级判定
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第八轮 X-1 开始

---

## 历史状态存档（十三）

- **更新者**：Opus 4.8（七轮完成：Terminal REPL 默认交互入口）
- **第七轮交付**：
  - **W-1 Terminal REPL**（tools/repl.py）：裸敲 `opsaxiom` 进交互态；自然语言当症状 top-3、
    数字选候选、导航档原地跑、内置词 help/list/info/run/resume/doctor/hub/record、
    Ctrl-C 中断回提示符、readline 历史、无 TTY 降级
  - **W-2**：docs/10 手册改 REPL 优先（子命令降为脚本附注）；info/resume 内置词
  - **W-3**：一键认证 outcome 结合反馈（👎→partial，负面记录照常签名入库）
  - **W-4**：README 快速上手改"opsaxiom 一个词"
- **全库现状**：73 Skill / 49 sim_verified、**267 pytest 全绿**、73 校验 / 67 仿真 全绿；
  CLI 子命令 {run,diagnose,doctor,skill,record,hub}，裸敲进 REPL。
- **需 Fable 七轮评审的重点**：
  1. REPL 的产品体验：自然语言当一等公民、数字选择、Ctrl-C 语义、无 TTY 降级是否到位；
     防镀金边界（不做 chatbot/多轮澄清）守得对不对
  2. REPL 在真 TTY 下的手感（评审可实敲 `opsaxiom` 试）——本轮测试覆盖分发逻辑，
     交互手感（提示符/中断/历史）建议人工过一遍
  3. 下一步大方向：IM 渠道接入（第八轮候选，webhook→diagnose→钉钉/飞书卡片，
     接缝 diagnose --json 已具备）、真实靶机执行器扩到 network/k8s、R-9 keyring 治理
- **交接给**：**Fable 5 —— 七轮评审**

---

## 历史状态存档（十二）

- **更新者**：Fable 5（六轮评审）
- 修 F-13(私钥进镜像/B10)、Terminal REPL 定为默认交互入口(docs/08 §4.2a)、第七轮任务书 W-1~W-4

## 历史状态存档（旧·六轮任务书发布时）

- **更新者**：Fable 5
- **阶段**：六轮评审完成，第七轮任务书已发（W-1~W-4：Terminal REPL）
- **六轮评审结论**：
  - V-1~V-6 验收通过，人侧飞轮闭环成立；docs/10 合格
  - **F-13 已修**：Dockerfile 构建期 keygen 把私钥烤进镜像（所有容器共享同一私钥）
    → 删除，运行时惰性生成；教训入 docs/07 **B10**（凭据/密钥永不进制品）
  - pull origin 标记实测过校验，三门信任模型 MVP 够用；keyring 治理记 R-9 open
  - 静态站优先维持；W-3 改进项：attest outcome 结合 👎 反馈
- **发起人决策**：**Terminal REPL 是产品默认交互入口**（终端最普遍，IM 是增强不是底座）。
  实测裸敲 `opsaxiom` 报错——缺口坐实。规格已写入 **docs/08 §4.2a**（自然语言一等公民/
  数字选择/导航档原地跑/Ctrl-C 语义/无 TTY 降级/防镀金边界）。
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第七轮 W-1 开始，**docs/08 §4.2a 是本轮必读**

---

## 历史状态存档（十一）

- **更新者**：Opus 4.8（六轮完成）
- **阶段**：第六轮 V-1~V-6 全部完成（人侧飞轮落地）
- **第六轮交付（人侧飞轮全部落地，docs/08 设计 → 实现）**：
  - **V-1 一键部署 + doctor**：install.sh(venv/软链/--offline)、Dockerfile、opsaxiom doctor 红黄绿自检
  - **V-2 经验捕获三通道**：skill from-session(会话审计→草稿)/record(投喂式,拒写)/new(向导) + lint(缺口清单)
  - **V-3 一键认证打通**：run 终点预填 attest(30秒签名)、attest --from-session、meta.json 留存
  - **V-4 Skills Hub 客户端**：hubtool(build-registry/init/search/pull 三门/push) + skills-community 隔离
  - **V-5 Hub 静态网站生成器**：registry→静态HTML(域浏览/搜索/决策树可视化/attestation)
  - **V-6 用户手册 docs/10 + 规范补遗**：docs/07 C7(分支顺序即优先级,F-12)/Cp(proc写法)/human 连接器
- **全库现状**：73 Skill / 49 sim_verified、**259 pytest 全绿**、73 校验 / 67 仿真 全绿。
- **需 Fable 六轮评审的重点**：
  1. 人侧飞轮的产品闭环是否顺（捕获→lint→晋级→push / pull→本地校验→用）——从运维视角审 docs/10
  2. **hub pull 三道安全门的信任模型**：本地重跑校验 + TOFU 验签 + draft 拒收，够不够？
     keyring 分发（谁签核 trusted.pub）是治理问题，是否要设计
  3. 经验捕获草稿质量：from-session 生成的线性骨架 + gap 清单，能否真正降低运维写作门槛
  4. 静态站 vs 动态服务的边界：先静态对不对，动态服务（账号/评论/API）何时上
  5. 下一步大方向：IM 渠道接入（第七轮候选，留存生命线）、真实靶机执行器扩到 network/k8s
- **交接给**：**Fable 5 —— 六轮评审**

---

## 历史状态存档（十）

- **更新者**：Fable 5（五轮评审）
- 73 Skill、F-12(分支顺序)修复、R-8 裁决维持现状、docs/08 人侧飞轮架构、第六轮任务书 V-1~V-6

## 历史状态存档（旧·五轮任务书发布时）

- **更新者**：Fable 5
- **阶段**：五轮评审完成 + 人侧飞轮架构设计已出（docs/08），第六轮任务书已发（V-1~V-6）
- **五轮评审结论**：
  - U-1~U-4 验收通过；proc"params+真实决策路由"形态获认可
  - **R-8 裁决：维持现状不动 schema**，kind:Playbook/artifact 等 Hub 渲染需求出现后再定
  - **F-12 已修**：obs/false-positive 分支顺序错误（阈值判据先于抖动判据）→ 教训 C7
    "分支顺序即优先级，特异判据在前"（V-6 落 docs/07）
  - collect mock 三要素（确定性/诚实标注/--from-file）通过；mock 永不参与 field 级证据
  - U-4 TOFU 过渡正确，终态信任锚在 registry keyring（docs/08 §3.3）
- **本轮新设计（发起人需求）**：docs/08-capture-hub-deploy.md ——
  经验捕获三通道（from-session/record/向导）、一键认证打通（run 终点预填 attest）、
  git-based Skills Hub（registry 仓库+客户端三道安全门+静态网站生成器）、
  一键部署三形态（install.sh/docker/离线包）+ doctor + 交互模型（入口 A 交互态/入口 B 告警→IM）
- **交接给**：Opus 4.8 —— 从 TODO-opus.md 第六轮 V-1 开始，**docs/08 是本轮必读**

---

## 历史状态存档（九）

- **更新者**：Opus 4.8（五轮完成）
- 73 Skill/8 域/49 sim_verified、CLI 打磨(resume/三选项/⟨?⟩)、collect、obs-sec-proc 12 Skill、Ed25519 签名

## 历史状态存档（八）

- **更新者**：Fable 5（四轮评审）
- 61 Skill、S13 求值冒烟、F-10(XID 92)修复、运行时 CLI 验收通过、第五轮任务书 U-1~U-5

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
