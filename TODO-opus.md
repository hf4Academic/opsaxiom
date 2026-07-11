# Opus 4.8 任务书

# 第八轮（Fable 布置，2026-07-11 七轮评审后）——告警入口 + 信任治理收尾

> 七轮裁决：F-14 已修（sid 单一事实来源）；F-15 诚实性教训（"已具备"必须实测）。
> Terminal 是底座（已成），本轮补"告警找人"的入口 B 最小闭环，并收尾信任治理。

## X-1 diagnose --json + 告警 webhook MVP（入口 B，docs/08 §4.2）
- `opsaxiom diagnose "<症状>" --json`：输出结构化候选（id/name/maturity/score/symptom），
  兑现 F-15。
- `tools/bin/opsaxiom-webhook`：stdlib http.server 收 Alertmanager 风格 webhook →
  取 alertname/description 拼症状 → diagnose → 组装通知卡片（候选 top-3 + 第一步
  指导 + `opsaxiom run <id>` 提示）→ 出站到钉钉/飞书机器人 webhook URL（urllib，
  两种卡片格式）。`--dry-run` 打印卡片不出站（测试用）；R11：卡片只含 Skill 信息与
  告警摘要，不含凭据。配 tests（本地起 server + 假告警 POST + dry-run 断言）。

## X-2 真实执行器扩面：k8s 只读
- sim `_ALLOW_LEAD`/`_is_readonly` 支持 `kubectl get/describe/logs/top`（只读白名单，
  显式拒 apply/delete/edit/scale/patch）；k8s 域挑 3 个诊断补 `mode: real` 场景
  （无集群环境跳过不失败——探测 kubectl 与 KUBECONFIG）。

## X-3 hub keyring 治理工具（关闭 R-9）
- `opsaxiom hub keyring list / add <pub> --name <who> / remove <who>`：管理本地
  keys/trusted/；`hub keyring export` 供 registry 侧合入。
- registry 侧签核流程写入 docs/08 §3.3 补段（维护者=签核人，PR 双人复核入 trusted.pub）。
  R-9 关闭记录进 REVIEW-QUEUE。

## X-4 field_verified 晋级判定
- promote.py 增 field 判定：≥3 份**独立** attestation（不同 attestor 且 env_fingerprint
  分桶不同，docs/05 §3）且验签有效 → 晋 field_verified；
  测试用 3 份合成签名 attestation 演练完整晋级（演练后清理，不留 fixture 污染）。

## X-5 收尾
- docs/07 新建 T 系列（工具类通则）：T-1 标识符单一事实来源（F-14）。
- HANDOFF 交接规则补"所有'已具备/已实现'表述写入前必须实测"（F-15）。
- README/HANDOFF 更新，交接 Fable 八轮评审。

进度勾选区（Opus 更新）：
- [x] X-1  - [x] X-2  - [x] X-3  - [x] X-4  - [x] X-5

---

# 第七轮（Fable 布置，2026-07-10 六轮评审后）——Terminal REPL【已完成，存档】

> 设计依据：**docs/08 §4.2a（Terminal REPL 规格，必读）**。发起人拍板：Terminal 是
> 产品默认交互入口（最普遍，不依赖 IM）。六轮裁决：F-13 已修（B10 密钥不进制品）。

## W-1 REPL 核心（tools/repl.py）
- 裸敲 `opsaxiom`（无子命令）→ 进 REPL；argparse required 改 False。
- 行为按 §4.2a 优先级：①非命令输入=症状→diagnose top-3(徽章+一行摘要)；
  ②纯数字=选上次候选→原地进导航档；③内置词 help/list/info/run/doctor/hub/record/quit；
  ④run 复用 runtime.Session 同进程跑，结束接一键认证，回提示符；
  ⑤Ctrl-C 中断当前 Skill 回提示符(提示 resume)，空闲时 Ctrl-C/quit 退出；
  ⑥readline 历史(~/.opsaxiom/history)；⑦无 TTY 打提示退出(自动化不被卡死)。
- 欢迎行带库存概况（N 个 Skill / M 已验证）；首次使用内联跑一次 doctor。
- 防镀金边界（§4.2a"不做的"）严格遵守。

## W-2 REPL 打磨与贯通
- `resume` 内置词：列出有 state.json 的会话，选择续跑。
- `info <id>`：渲染 Skill 概况（徽章/症状/树的节点数/attestation 数/cautions 前 3 条）。
- demos/repl-session.answers 式脚本驱动（IO 抽象复用），供测试与演示。
- docs/10 手册第二章改写为 REPL 优先（子命令降为"脚本/自动化用法"附节）。

## W-3 认证 outcome 结合反馈
- run 终点若反馈是 👎/negative → attest 预填改问 outcome(partial/failed)；
  👍 → 维持 resolved。负面 attestation 照常签名入库（docs/05 允许，是宝贵信号）。

## W-4 收尾
- README 快速上手改为"opsaxiom 一个词"；HANDOFF 交接 Fable 七轮评审。
- 全量回归（校验/pytest/仿真）+ REPL 端到端演示脚本入 tests。

进度勾选区（Opus 更新）：
- [x] W-1  - [x] W-2  - [x] W-3  - [x] W-4

---

# 第六轮（Fable 布置，2026-07-10 五轮评审后）——人侧飞轮【已完成，存档】

> 设计依据：**docs/08-capture-hub-deploy.md（必读，本轮宪法级输入）**。
> 五轮裁决：R-8 维持现状不动 schema；F-12 已修（分支顺序=优先级）。

## V-1 一键部署 + doctor
- `install.sh`：venv 装依赖、软链 tools/bin/* 进 PATH、初始化 ~/.opsaxiom、末尾自动跑 doctor；
  `--offline` 模式（用预置 wheels/ 目录，不出网）。
- `opsaxiom doctor`：检查 python 版本、依赖齐全、密钥目录权限、tools/bin 可执行、
  （可选连接器探测 ssh/kubectl/mysql 是否在 PATH），红黄绿输出。
- Dockerfile（python-slim 基座，入口即 opsaxiom）。

## V-2 经验捕获三通道（docs/08 §1）
- `opsaxiom skill from-session <sid>`：审计 jsonl → skill.yaml 草稿（check 带真实命令；
  输出摘要 → 同步生成 sim 场景 node_ctx 草稿；done.summary 用人的终态描述占位）→ skills-drafts/。
- `opsaxiom record start/exec/stop`：投喂式记录会话（exec 仅限 _is_readonly 白名单），
  产物走同一条"审计→草稿"管线。
- `opsaxiom skill new`：向导式问答生成（按 docs/07 规则边问边校验）。
- `opsaxiom skill lint <draft>`：validate + 缺口清单（缺 otherwise/caution/rollback/tests 逐条列出）。

## V-3 一键认证打通（docs/08 §2）
- run 终点在 feedback 之后追问 attest（[y/N]，默认 N）；y → 从会话预填
  outcome/mode/rollback_exercised/skill/version，仅问 os-family 与规模两个分桶 → 签名落盘。
- `opsaxiom attest --from-session <sid>`（等价异步入口）。
- 脚本模式（--answers）兼容：answers 里 `<terminal_id>:attest: {os_family: rhel, scale: 47}`。

## V-4 hub 客户端（docs/08 §3，git-based）
- `opsaxiom hub init <registry-git-url>`（本地缓存 ~/.opsaxiom/hub/）、
  `hub search`（本地 index.json）、`hub pull <id>`（→ skills-community/，三道安全门：
  本地重跑 validate / 验签对 keyring / draft 默认拒收）、`hub push <id>`（打包出分支或 bundle）、
  `hub sync`（index + keyring 更新提示）。
- 用本仓库自身生成一个演示 registry（tools/hubtool build-registry skills/ → /tmp 或 registry/ 子目录）
  供端到端测试——不依赖外网。
- index.json 生成器归入 `tools/hubtool`。

## V-5 Hub 静态网站生成器（docs/08 §3.4）
- `tools/hubsite/build.py`：registry → 静态 HTML（首页域浏览+关键词搜索、
  Skill 详情页：树的文本可视化、cautions、徽章、attestation 列表与验签状态）。
- 无 JS 框架依赖，纯模板（可用 string.Template/f-string），离线可开。
- 对演示 registry 构建出完整站点，产物截图路径写进 PR/commit 说明。

## V-6 用户手册 + 规范补遗 + 收尾
- `docs/10-user-guide.md`：装/用/沉淀/交换四章 + 一页起步卡（docs/08 §4.3 规格）。
- docs/07 补：**C7 分支顺序即优先级（F-12）**、proc 域写法规范（R-8 裁决）、
  connectors:[human] 说明。
- README 更新（部署三形态 + hub），HANDOFF 交接 Fable 六轮评审。

进度勾选区（Opus 更新）：
- [x] V-1  - [x] V-2  - [x] V-3  - [x] V-4  - [x] V-5  - [x] V-6

---

# 第五轮（Fable 布置，2026-07-09 四轮评审后）——打磨与扩面【已完成，存档】

> 规范依据新增：docs/03 §7.6d（S13 求值冒烟，已由 Fable 实现）、docs/07 B9（枚举清单双向核对）。
> F-10（XID 92 误归）已由 Fable 修复并重晋级。

## U-1 导航档 CLI 打磨（四轮评审的 4 个产品项）
- 审计补全：verify 结果(passed/failed)与粘贴输出摘要(截断 200 字符)入 jsonl；
- action 未确认时给三选项：跳过此步走其他分支 / 升级人工 / 退出（而非直接 escalate）；
- 断点续跑：`opsaxiom run --resume <sid>` 从审计恢复会话至上次节点；
- 模板渲染缺失字段显示 `⟨?⟩` 占位而非空串（runtime.render 的 None 分支）。

## U-2 opsaxiom-collect 实现（F-11，slow-node/gpu-util-low 依赖）
- 参照 quarantine/deploy 品质：step-time / node-metrics / gpu-trace 三个子命令，
  无 GPU 环境可测（mock 数据源 + --from-file）。同时在 docs/07 E 清单补第 6 项：
  "引用 opsaxiom-* 自研工具时，工具必须已存在或同轮排期"。

## U-3 obs / sec / proc 域 Skill（合计 12 个）
- obs×5: alert-storm, false-positive, metrics-missing, target-down, incident-timeline(proc 联动)
- sec×4: abnormal-login, bruteforce, cert-expiry-inventory, vuln-scan-triage
- proc×3: change-ticket-gen, incident-report-gen, shift-summary
  （proc 域是纯生成类——注意：无命令无分支的 Skill 形态可能挑战 schema，
   表达不了就记 REVIEW-QUEUE，别硬凑决策树）
- 全部走 docs/07 全规则 + context_walk 场景 + promote。

## U-4 attestation 签名落地
- 用 Ed25519(python cryptography 或 nacl，若环境缺则 hashlib HMAC 过渡并注明)替换 UNSIGNED-TODO；
  opsaxiom-attest 生成密钥对(~/.opsaxiom/keys)、签名、校验器验签(无公钥时 WARN)。

## U-5 收尾：HANDOFF + 提醒切回 Fable 五轮评审

进度勾选区（Opus 更新）：
- [x] U-1  - [x] U-2  - [x] U-3  - [x] U-4  - [x] U-5

---

# 第四轮（Fable 布置，2026-07-09 三轮评审后）——里程碑轮：从资产到产品【已完成，存档】

> 前三轮建的是资产（51 Skill、校验/仿真/晋级/attest 流水线）。本轮开始造**用户真正敲的东西**：
> 导航档运行时 CLI。这是 docs/01 §2 三档交互的第一档落地，也是"让运维工程师用一天后
> 不愿卸载"的 MVP 起点。规范依据新增：docs/03 §7.6c（R-7 裁决）、docs/07 B7。

## T-1 运行时 CLI 导航档 MVP（本轮核心，可多次提交）
- `tools/bin/opsaxiom` 子命令 `run <skill-id> [--param k=v]...`：
  加载 Skill → 逐节点交互执行（导航档语义，黄金准则 R3/R5）：
  - check：打印标题+命令+cautions → 人执行后粘贴输出（或 `--real` 时白名单只读命令自动执行，
    复用 run_sim 的 _is_readonly/解析器/求值器）→ 机器判分支 → 下一步；
  - ask：呈现 options 供选择，答案按 binds 绑定变量；
  - action：**渲染变更简报**（blast_radius/watch/abort_if/est_downtime + 渲染后的 run/rollback
    命令原文）——导航档只指导不执行（R6），人确认完成后继续 verify 指导；
  - done/escalate：渲染 summary（模板按 §7.4/§7.6c 求值）→ feedback.ask 单比特反馈 →
    提示可 `opsaxiom-attest` 沉淀。
- 全程审计：会话记录（节点序列/输入输出摘要）落 `~/.opsaxiom/sessions/<sid>.jsonl`。
- 用 disk-full 与 mysql-slow-query 各录一个演示脚本(非交互 --answers 文件驱动)进 tests。

## T-2 Skill 匹配（docs/04 §4 的最小实现）
- `opsaxiom diagnose "<症状描述>"`：L1 关键词分类(8 选 1) + 域内 L3 入口症状子串/分词匹配 →
  列候选 Skill(带 maturity 徽章与证据级) → 选定后进 T-1 的 run。不引入 embedding，先关键词。

## T-3 实施 R-7 渲染契约（docs/03 §7.6c）
- 模板渲染引擎：`{{output.<scalar>}}` 按节点 parser 的 scalars 声明解析；`{{rows[0].x}}` 等
  字段引用复用 exprlang 求值；FIELD 校验扩展覆盖模板引用。summary 里恢复此前被移除的标量引用。

## T-4 mysql 版本限定修复（三轮评审 nit）
- 5 个 mysql Skill 的 platforms 补 `versions: ">=8.0"`；关键 check 加 5.7 降级命令 caution
  （sys.innodb_lock_waits 等）。docs/07 增补规则：**用到版本特有表/命令必须声明版本限定**。

## T-5 aicomp 域 10 个 Skill（原始愿景的引爆点域）
- 按 docs/04 §5.4 高频叶子：xid-error、ecc-error、fell-off-bus、thermal-throttle、
  ib-link-down、nccl-allreduce-slow、nccl-hang、job-hang、slow-node、gpu-util-low。
- nvidia-smi/dcgmi/ibstat 类命令的解析器契约入 parser_fields.yaml；严守 docs/07 全部规则；
  各附 context_walk 场景走 promote。XID 错误码表（13/31/48/63/64/79...）的含义要准——这是
  该域最核心的领域知识，写进 cautions。

## T-6 收尾：HANDOFF + 提醒切回 Fable 四轮评审

进度勾选区（Opus 更新）：
- [x] T-1  - [x] T-2  - [x] T-3  - [x] T-4  - [x] T-5  - [x] T-6

全部完成。61 Skill(host20/k8s10/network11/middleware10/aicomp10)、37 sim_verified、
运行时导航档 CLI 落地(run+diagnose)。校验 61/61、pytest 193/193、仿真 43/43 全绿。
本轮修了一个求值器 or 短路 bug(影响运行时所有 or 表达式)。

---

# 第三轮（Fable 布置，2026-07-09 二轮评审后）【已完成，存档】

> 规范依据新增：docs/03 §7.6a/§7.6b（F-8 投影语义、R-5 字段契约）、docs/05 证据分级、docs/07 B6。

## Q-1 实施 S12：投影语义静态检测（最高优先——F-8 类错误今天校验器挡不住）
- exprlang 校验路径中检测："`[]` 投影未经聚合函数（max/min/count/any/all/avg/sum）包裹
  即参与 and/or 或与另一投影比较" → ERROR，报错信息指向 docs/07 B6。
- 负向测试用例至少 4 个（含 F-8 的两个原始写法）；全库 41 Skill 重新过校验必须全绿。

## Q-2 解析器注册表带输出字段声明 + assert 字段校验（实施 R-5）
- 解析器注册时声明输出字段清单（含 R-5/F-8 累积的健康与派生字段：
  service_active、mount_rw、rollout_succeeded、unready_pods、inconsistent_ports、
  deny_hit_count、tcn_rate、pcent_before[引擎快照] 等）。
- 新校验（先 WARN 一轮）：branch.when / verify.assert 引用的字段须在
  对应解析器声明的输出 ∪ facts ∪ params ∪ 引擎快照(`*_before`) 内。
- 实现其中至少 5 个高频解析器（systemctl is-active、df 前后对比、kubectl rollout status、
  stp brief、acl hits——linux/kubectl 侧优先，网络侧可先 ntc 映射）。

## Q-3 真实靶机执行器 v1（sim 从 context_walk 走向 real）
- run_sim 增加 `mode: real` ：在本地沙箱（无 root）真实执行 linux 平台的 discovery/check 命令
  （限白名单只读命令），接真实解析器，走真实分支——先覆盖 disk-full 与 3 个纯诊断 host Skill。
- 晋级证据自动记 `evidence: real_roundtrip` / `context_walk`（promote.json 已有 scenarios，
  增加 evidence 字段，docs/05 的分级展示以此为源）。

## Q-4 attestation CLI 骨架（docs/05 §2 的 `opsaxiom attest`）
- `tools/bin/opsaxiom-attest`：交互式生成 attestation YAML（含 env_fingerprint 脱敏分桶、
  deviations、rollback_exercised），落到 `<skill>/attestations/`，签名先留 TODO 桩。
- 校验器新增：attestations 目录格式校验（append-only 由 CI 保证，先不做）。

## Q-5 middleware 域 10 个 Skill（mysql/redis/kafka 优先，按 docs/04 §5.5 高频叶子）
- 严格执行 docs/07 全部规则（尤其 B6）；每个附 ≥1 可执行 context_walk 场景并走 promote。

## Q-6 收尾：HANDOFF + 提醒切回 Fable 三轮评审

进度勾选区（Opus 更新）：
- [x] Q-1  - [x] Q-2  - [x] Q-3  - [x] Q-4  - [x] Q-5  - [x] Q-6

全部完成。51 Skill(host20/k8s10/network11/middleware10)、27 sim_verified、
校验 51/51、pytest 160/160、仿真 32/32 全绿。新缺口 R-7、F-9(留 Fable)。

---

# 第二轮（Fable 布置，2026-07-09）【已完成，存档】

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
