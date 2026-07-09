# Skill Schema v0.1

> 这是"法律层"：所有约束由 `schema/skill.schema.json`（结构校验）+ 语义校验规则（本文 §4）
> 共同强制。一个 Skill = 一个目录，其中 `skill.yaml` 是唯一权威来源（single source of truth）。

## 1. 目录布局

```
skills/<domain>/<slug>/
├── skill.yaml          # 权威定义（本 schema）
├── guide.md            # 可选：给人读的背景知识（不参与执行）
├── tests/              # 仿真测试场景（晋级 sim_verified 必备）
│   └── *.yaml
└── attestations/       # 社区验证记录（append-only，见 05-certification.md）
    └── *.yaml
```

## 2. 顶层结构

```yaml
apiVersion: skill/v0.1
kind: Diagnostic | Change | Hybrid      # 排障类 / 变更类 / 混合
metadata:
  id: host.storage.disk-full            # = taxonomy 路径的点分形式，全局唯一
  name: 磁盘空间耗尽排查与处置
  taxonomy: host/storage/capacity/disk-full
  version: 0.3.0                        # semver；MAJOR 变更 = 决策树结构性改变
  maturity: draft                       # draft | sim_verified | field_verified | certified
                                        # 该字段由认证流水线写入，人工/模型不得直接修改
  platforms:                            # 适用范围声明，运行时与环境事实匹配
    - {os: linux, family: [debian, rhel]}
  authors: [...]
  provenance:
    generated_by: claude-opus-4-8       # 生成者
    reviewed_by: [claude-fable-5]       # 评审者（模型或人）
  expires_review: 2027-01-01            # 时效：过期未复审自动降一级（防腐烂）

requirements:
  capability_level: high_risk_write     # 本 Skill 需要的最高能力级
  connectors: [ssh]
  facts: [os.family, fs.mounts]         # 依赖的环境事实（缺失时先采集）

discovery:                              # 只读探针，会话开始时执行，结果注入决策树上下文
  - id: df
    run: {linux: "df -B1 --output=target,size,used,avail,pcent,itotal,iused"}
    parser: table/df-v1                 # 引用解析器库中的解析器

tree:                                   # 决策树（见 §3）
  entry: <node-id>
  nodes: [...]

tests:
  - scenario: tests/log-growth.yaml
    expect_path: [entry-node, ..., done]
    rollback_assert: true               # 该场景是否断言回滚路径

feedback:
  ask: "问题解决了吗？"                  # 会话结束的单比特反馈，写入 attestation
```

## 3. 决策树节点类型

所有节点共有字段：`id`、`title`、`cautions[]`（注意事项，导航档下逐条呈现给人）。

### 3.1 `check` —— 只读检查
```yaml
- id: check_inode
  type: check
  run: {linux: "df -i --output=target,ipcent"}
  parser: table/df-inode-v1
  branch:                               # 分支条件必须机器可求值（R7）
    - when: "max(rows[].ipcent) > 90"   # 受限表达式语言，见 §5
      goto: inode_exhaustion
    - when: "max(rows[].ipcent) <= 90"
      goto: check_big_files
  otherwise: escalate                   # 兜底分支必填
  cautions:
    - "NFS 挂载点的 inode 数据可能不准确，如目标是 NFS 请以服务端为准"
```

### 3.2 `action` —— 写操作（约束最重的节点）
```yaml
- id: quarantine_big_files
  type: action
  risk: high                            # low | medium | high | critical
  preflight:                            # risk >= medium 必填（变更简报）
    blast_radius: "仅影响所列文件的可访问性，不影响运行中进程已打开的句柄"
    watch:                              # 操作中人/Agent 盯的指标
      - {run: {linux: "df -h {{mount}}"}, expect: "使用率下降", interval: 10s}
    abort_if:
      - "任一业务健康检查失败"
    approval: required                  # required | auto(仅 risk=low 允许)
  dryrun:
    run: {linux: "du -sh {{files}} && echo '将移动以上文件到隔离区'"}
  run:
    linux: "mkdir -p {{qdir}} && mv {{files}} {{qdir}}/ && ln -s {{qdir}}/MANIFEST ..."
  rollback:                             # 必填，type 见 02-rollback-design.md
    type: inverse
    run: {linux: "opsagent-restore {{qdir}}"}
  verify:                               # 必填：操作后断言
    run: {linux: "df -B1 --output=pcent {{mount}}"}
    expect: "pcent < {{threshold}}"
    on_fail: rollback                   # rollback | escalate
  goto: verify_service
```

### 3.3 `ask` —— 向人索取信息（机器无法获取的判断/授权）
```yaml
- id: confirm_deletable
  type: ask
  question: "以下文件确认可移出（业务上不再需要）吗？{{files}}"
  options: [{label: 确认, goto: quarantine_big_files}, {label: 不确认, goto: escalate}]
```

### 3.4 `escalate` / `done` —— 终止节点
- `escalate`：汇总已采集事实与走过的路径，升级给强模型或人（升级 trace 归档为新 Skill 原料）。
- `done`：输出结论摘要，触发 `feedback.ask`。

## 4. 语义校验规则（结构校验之外，校验器必须实现）

| 规则 | 内容 | 违反后果 |
|---|---|---|
| S1 | 每个 `action` 必有 `rollback` 且平台键与 `run` 一致 | 拒绝入库 |
| S2 | `risk >= medium` 必有 `preflight`（含 watch、abort_if）与 `approval: required` | 拒绝入库 |
| S3 | 每个 `action` 必有 `verify` | 拒绝入库 |
| S4 | 每个 `check` 必有 `otherwise` 兜底 | 拒绝入库 |
| S5 | 所有 `when` 表达式必须通过受限表达式语言解析（§5），禁止自由文本 | 拒绝入库 |
| S6 | 所有命令必须通过对应平台的语法树校验（network 域强制，host 域尽力） | 拒绝入库 |
| S7 | `goto` 引用必须存在；树必须无不可达节点、无无限环 | 拒绝入库 |
| S8 | `maturity >= sim_verified` 要求 tests 非空且至少一个 `rollback_assert: true` | 拒绝晋级 |
| S9 | 模板变量 `{{x}}` 必须在 facts、discovery 输出或 ask 答案中有来源 | 拒绝入库 |
| S10 | `maturity` 与 `attestations/` 记录一致性由流水线核算，不接受手工声明 | CI 覆写 |

## 5. 受限表达式语言（branch when）

只允许：解析器输出字段引用、数值/字符串比较、`and/or/not`、
聚合函数 `max/min/count/any/all`、增量函数 `delta(field, interval)`（用于计数器判读）。
**不允许**：自由文本、正则以外的模糊匹配、模型判断。表达式在编译期静态检查。

设计动机（R7）：分支求值是纯代码行为，运行时模型只在解析器无法覆盖输出时被请求做
"输出属于哪个已知分支"的分类，且其结论要与表达式求值交叉验证。

## 6. 版本与兼容

- `skill/v0.1` 期间允许 schema 破坏性演进，但每次演进必须提供迁移脚本（tools/migrate/）。
- Skill 的 `version` 与 `maturity` 绑定：结构性修改（MAJOR）自动重置 maturity 为 `draft`。

## 7. v0.2 决议（Fable 裁决，2026-07-09；实施见 TODO-opus 第二轮）

针对首轮执行暴露的 R-1~R-4 与评审新发现，v0.2 做如下演进。**在实施完成前，
本节是规范的一部分**——新写的 Skill 应按此准备，校验器升级后旧 Skill 统一迁移。

### 7.1 变量声明（裁决 R-1：采纳）
- `metadata.params`: `[{name, source: alert|user|derived, desc}]` —— Skill 入参声明。
- `ask` 节点新增必填 `binds: <varname>`（无产出的 ask 允许 `binds: null`）。
- 变量合法来源 = `facts ∪ discovery.<id> ∪ params ∪ ask.binds ∪ builtin{sid}`。
- 迁移完成后 **S9 升为 ERROR**。

### 7.2 verify 断言机器化（裁决 R-2：采纳变体）
- `verify` 拆为：`assert`（必填，受限表达式，S5 同规则强制）+ `note`（可选散文，给人看）。
- `preflight.watch[].expect` 与 `abort_if` **保留散文**：它们的第一读者是执行中的人（导航/协驾档），
  机器化收益低；但引擎在自驾档执行时须把 `abort_if` 视为"任一条件模型判定成立即中止"，
  且该判定结果必须记入审计日志。

### 7.3 聚合函数（裁决 R-3：采纳）
- 允许函数集增加 `avg`、`sum`。`count(...) >= k` 仍是"持续超阈值"的推荐写法（抗尖峰），
  写入生成规范。同步修改 exprlang 的 _FUNCS 与求值器。

### 7.4 模板变量文法（裁决 R-4：统一到表达式文法）
- `{{...}}` 内部采用与 branch.when **相同的字段引用文法**（点路径 + `[N]` 下标 + `[]` 投影），
  渲染引擎直接复用 exprlang 的字段求值。`{{rows0_comm}}` 这类拍平别名废止，迁移为 `{{rows[0].comm}}`。
- 命名空间：discovery 输出以 `{{discovery.<id>.<field>}}` 访问；当前节点输出可用裸 `{{rows...}}`。

### 7.5 新增语义规则 S11：回滚不得为空转（评审发现 F-2）
- `rollback.run`（及 snapshot.run）若实质为 `echo`/注释类空转命令 → ERROR；
  例外：`human_only: true` 的节点允许 `rollback.advisory: true` + 说明文字，
  表示"回滚方案是给人的操作指引而非可执行命令"（fs-readonly 的 fsck 属此类）。
- 动机：不可执行的回滚通过 S1 是形式合规、实质违宪（R1）。

### 7.6 facts 单位与命名注册表（评审发现 F-4）
- 新建 `docs/06-facts.md`：facts 的权威清单，含**单位**（bytes/KB/%/count）、类型、采集命令。
- 表达式里跨源比较（如 `rows[0].rss > mem_total * 1024 * 0.4`）必须能从注册表推出单位一致，
  否则校验器告警。首批注册：os.family, cpu.cores, mem.total(MB), fs.mounts, storage.devices,
  host.arch, host.virtualization, kernel.version, k8s.context, device.platform, device.version, bgp.local_as。
