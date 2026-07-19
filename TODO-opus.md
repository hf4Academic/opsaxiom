# Opus 4.8 任务书

# 第十四轮（Fable 布置，2026-07-19）——I 系列：远程接入 + 本地化 Skill

> 发起人已批准两份设计：**docs/12（远程接入与凭证管理）** 与 **docs/13（本地化
> Skill：linkbook/overlay/fork 三层）**。开工前把两份设计读完——本任务书只写
> "做什么和验收标准"，"为什么"都在设计文档里，吃透再动手。
>
> **安全红线（每一条都有对抗测试要求，虚实现比不实现严重）**：
> - R-A1 清单只存引用：任何文件出现明文凭证 → 拒绝加载（access.py 已立标）；
> - R-A2 凭证不出内存：不落盘、不入日志、不进卷宗、送模型前 redact；
> - R-A3 自动通道只读：连接器执行前必过执行门白名单（_is_readonly / 语法库
>   前缀 / kubectl 动词 / GET-only），写操作结构性进不来；
> - overlay 不碰树：出现 run/branch/when 即拒绝加载（徽章诚实性）；
> - 个人层不出门：打包器 + CI 双重拒收 visibility:local 与 local. 前缀。
>
> 节奏照旧：每条目一个 [I-n] commit，全量回归绿再提交；新模块必须带对抗测试。

## I-0（Fable 已完成，你直接用，不要改）
- docs/03 §7.1：`metadata.params.source` 新增枚举 `local`（含缺值降级语义）。
- `tools/access.py`：targets.yaml 加载 + 三红线 + P0 凭证解析骨架（agent/
  ssh_config/kubeconfig/file，keyring 留口）。**这是金标准——后续所有接入代码
  的错误信息风格、红线处理方式（整文件拒绝而非部分放行）照此办理。**
- `tools/tests/test_access.py`：12 条对抗测试，照这个密度写你的。

## I-1 ssh 连接器 + 执行门接线（协驾档出本机的第一步）
- `tools/connectors/ssh_conn.py`：paramiko 连接（复用 gitpush 的依赖），支持
  auth=agent（SSH_AUTH_SOCK）/ssh_config（paramiko.SSHConfig 解析 ProxyJump/
  IdentityFile）/file。无 tty、禁 agent 转发、禁端口转发、超时 10s。
- **执行门唯一入口** `tools/gate.py`：`run_remote(target_name, cmd)` =
  load_targets → 授权检查（I-2 的 trust）→ 白名单（ssh 用 sweep._is_readonly）
  → resolve 凭证 → 连接器执行 → 审计落盘（命令/输出/目标/时刻）→ 返回输出。
  连接器自己不做任何安全判断——安全全在门里，这是 docs/12 §4 的架构决定。
- 对抗测试：写命令被拒（rm/tee/重定向）、param 注入被拒（T-3 复用）、
  未授权目标被拒、凭证对象不出现在审计文件里。
- 真机验证：本机 sshd 对 localhost 跑通全链路（CI 环境没有 sshd 就 skip，
  但本机开发必须真跑过一遍并在 commit message 里写明）。

## I-2 per-target 授权 + 审计扩目标维度
- sweep.py 的 trust.yaml 扩成 `{target: {granted_at, ttl_days: 30, scope: readonly}}`；
  is_trusted/grant_trust 加 target 参数（本机=LOCAL 兼容不破）；过期视同未授权。
- `opsaxiom target revoke <name>`；`target list` 显示授权剩余天数。
- facts.py/incident 审计已存 target 的复查补齐：每条远程命令能从卷宗追溯到
  目标与时刻。

## I-3 target CLI：add / import-ssh-config / doctor
- `target add <name>`：交互向导（connector/host/auth 自动试探——agent 里有钥匙
  就默认 agent，config 里有 Host 条目就默认 ssh_config；reach 标签询问）。
- `target import-ssh-config`：解析 ~/.ssh/config 的 Host 条目批量生成（跳过
  通配符条目），生成前逐条列出让人确认。
- `target doctor`：逐目标 连通→凭证→权限级别 三段体检，🟢🟡🔴；同 reach 标签
  集体不通时输出"网络前置未就绪（先连 VPN）"而不是逐台报错（docs/12 §4.5）。
  权限检测：ssh 目标上跑 `id`，root/sudo-all → 🟡 建议低权账号。

## I-4 enroll 首次开通（docs/12 §3.5）
- `target enroll <name> --host <ip> [--user root] [--no-create-ro]`：
  ① 本机无密钥则 ssh-keygen ed25519（提示可设口令）；② paramiko 密码认证
  一次性上门（getpass 输入，变量用完 del，不进任何文件/日志——写对抗测试：
  enroll 后全盘 grep 不到密码）；③ 建 opsaxiom-ro + 装公钥 + sudoers 白名单；
  ④ 换密钥验证 + 写 targets.yaml。
- **sudoers 白名单生成器** `tools/authoring/gen_sudoers.py`：扫全库 skills/
  的 linux 命令，抽首个二进制（含 sudo 前缀的）生成 /etc/sudoers.d/opsaxiom-ro
  内容；带测试（对 205 库跑出的清单人工抽查后固化为快照测试）。
  这是"技能库即权限清单"（docs/12 §5.6），发布物之一。
- `--from hosts.txt` 批量。

## I-5 network + http 连接器
- `network`：paramiko 行协议，平台提示符适配 cisco_ios/huawei_vrp（禁 enable/
  system-view 等提权与配置模式命令——运行时再过一遍语法库前缀白名单，S6 同源）。
- `http`：urllib，仅 GET；base 来自 targets.yaml，路径来自 Skill 声明；
  自签证书场景 `verify: false` 显式声明才放行且 doctor 黄牌。
- 各带对抗测试（配置模式命令被拒 / POST 被拒 / 路径逃逸被拒）。

## I-6 P1 钥匙串 cred.py + `opsaxiom cred set/rm/list`
- 优先 OS keyring（SecretService/Keychain，import 失败自动降级）；降级路径：
  age 不引新依赖的话用 cryptography.fernet + 主口令（getpass），文件 0600。
- access.resolve 的 keyring: 分支接线。list 只显示条目名不显示值。

## I-7 混合取证计划（sweep 扩远程 + incident 接入）
- evidence/sweep：取证计划按 target 分组——可自动（有授权+可达）→ gate 并行执行
  入事实库；不可自动 → 该目标渲染导航档粘贴块（现有机制），同屏混合输出。
- reach 不可达的交互：提示"先连 VPN 按回车重试 / skip 转粘贴"（docs/12 §4.5），
  断点续跑。
- 端到端测试：mock 两个目标（一通一不通），断言混合计划形态正确。

## I-8 linkbook（docs/13 §1，L-1）
- `~/.opsaxiom/linkbook.yaml` 加载（taxonomy 最长前缀匹配 + "*" 全局）；
  REPL/卷宗展示 `📌 你的相关页面：…`。就这么小，别做大。

## I-9 overlay 加载器（docs/13 §2，L-2 核心）
- `tools/overlay.py`：加载 `~/.opsaxiom/overlays/<skill-id>.yaml`，红线校验
  （出现 run/branch/when/节点增删 → 拒绝加载并说明），合并三类内容：
  params(source:local 填值)/notes(按 node id 贴 links+caution)/answers(ask 预填)。
- 展示合并：REPL 与卷宗中本地内容一律 📌 前缀；node id 失配 → 跳过 + 黄牌
  （不阻塞）。params 缺值 → 该 check 降级粘贴块（docs/03 §7.1 语义）。
- 对抗测试：overlay 试图改 when 被拒 / 改 run 被拒 / 注入 shell 元字符的
  local param 被拒（T-3）/ 失配节点不阻塞。

## I-10 fork 派生（docs/13 §3，L-3）
- `skill fork <base-id>`：拷到 ~/.opsaxiom/skills-local/，id 加 local. 前缀，
  写 derived_from + visibility:local + maturity:draft。
- 本地流水线：validate/run_sim/promote 对 skills-local 全可用（路径解析注意
  ROOT 外目录——promote 的 relative_to 要兼容）。
- **出门拦截**：hubtool.hub_push 与 build_registry 遇 visibility:local 或
  local. 前缀 id → 拒绝并说明；registry CI 同规则（.github/workflows 加一步）。
  对抗测试：故意把 fork 拷进 skills/ 再 build → 必须被拒。

## I-11 skill doctor + --share 导出剥离（L-4）
- `skill doctor`：overlay 引用失配节点列表；fork 落后 base 版本提示 + diff 指引。
- 卷宗/报告导出 `--share`：剥离全部 📌 内容与 linkbook 链接；redact.py 增补
  内网 URL pattern 兜底。测试：--share 产物 grep 不到 overlay/linkbook 中的域名。

## I-12 收尾
- docs/10 用户指南补"接入你的设备"与"个性化"两章（说人话，走查式）；
- README 状态更新；HANDOFF 更新 + 交回 Fable 评审；全量回归三绿。

## 排序与依赖
I-1→I-2→I-3 是主线（先能连、再有授权、再好用）；I-4/I-5/I-6 并行块；
I-7 依赖 I-1..I-3；I-8 独立随时可做（适合热身）；I-9→I-10→I-11 是本地化线，
依赖仅 I-0。**建议顺序：I-8 热身 → I-1..I-3 → I-9 → 其余。**
