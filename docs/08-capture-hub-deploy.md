# 经验捕获 · Skills Hub · 一键部署（五轮评审 Fable 设计）

> 本文回答三个产品问题：**运维人员怎么把经验变成 Skill？怎么与社区交换可信 Skill？
> 怎么在私有环境一键部署并日常使用？** 这三件事共同构成飞轮的"人这一侧"：
> 前四轮建的是"模型侧"（生成→校验→仿真→评审），本文设计"人侧"
> （使用→沉淀→认证→分享），二者闭环才是社区。
> 实施排期见 TODO-opus.md 第六轮（V 系列）。

---

## 1. 经验捕获：把日常排查变成 Skill

### 1.1 设计原则

- **捕获点越靠近工作现场，成本越低**。运维人员不会"事后专门写 YAML"——
  必须在他排查的当下顺手捕获。
- **三条捕获通道，覆盖三种日常形态**（按摩擦从低到高）：

### 1.2 通道一：会话衍生（`opsaxiom skill from-session <sid>`）——最低摩擦

导航档会话审计（`sessions/<sid>.jsonl`）已经记录了每一步的命令、输出摘要、判读、
人的决策。这就是**现成的经验底稿**：

- 跑某 Skill 时人偏离了树（skip 了某步、escalate 后自己解决了）→ 偏离本身就是
  新变体/新 Skill 的线索（docs/05 早已把 deviations 定义为"决策树改进线索"，现在兑现它）。
- `from-session` 把审计回放成 **skill.yaml 草稿**：check 节点带真实命令与真实输出样例
  （输出样例直接变成 sim 场景的 node_ctx！）、人最终结论变成 done.summary 初稿、
  自动填 provenance（generated_by: human-session）。
- 草稿落 `skills-drafts/`，跑 `opsaxiom skill lint`（= validate + 缺口清单：
  "还差 otherwise / 还差 caution / rollback 未填"），人补完 → 正常晋级流水线。

### 1.3 通道二：记录模式（`opsaxiom record`）——排查没走任何 Skill 时

`opsaxiom record start` 开一个记录会话：人照常在自己终端排查，把关键命令+输出
粘贴进来（或用 `record exec <cmd>` 代跑只读命令自动留痕），结束时 `record stop`
→ 与通道一同一条"审计→草稿"管线。**不做 shell 全量抓取**（噪声大且有 R11 凭据风险），
只收人主动投喂的步骤——这同时是隐私边界。

### 1.4 通道三：向导（`opsaxiom skill new`）——从零结构化输入

交互式问答（症状叫什么？第一步查什么命令？看哪个字段？分几种情况？每种情况结论是？），
按 docs/07 规则边问边生成，问完即出可校验的 skill.yaml。适合把"脑子里的老经验"倒出来。

### 1.5 质量门不降级

三条通道产出的都是 **draft**，一律过既有流水线（validate S1-S13 → sim → promote）。
经验捕获降低的是**写作成本**，不是**认证门槛**——这是社区可信的底线。

---

## 2. 一键认证：从"跑完了"到"沉淀了"零距离

现状 attest 要手敲 8 个 flag，等于没有。设计：

- **run 终点直接接单**：done/escalate 后，在既有"👍/👎"反馈之后追问一句
  `要把这次验证沉淀为社区凭据吗？[y/N]`。y → 从会话上下文**预填全部字段**
  （skill/version/outcome←路径终态、mode←会话模式、rollback_exercised←审计里是否走过
  rollback_guide），人只需补 os-family 和规模两个分桶 → Ed25519 签名落盘。全程 <30 秒，
  兑现 docs/05 "30 秒表单"的承诺。
- 等价命令：`opsaxiom attest --from-session <sid>`（IM/异步场景补交用）。
- **env_fingerprint 仍只收分桶**（R11），预填逻辑不碰任何主机名/IP。

---

## 3. Skills Hub：可信技能的交换机制

### 3.1 核心决策：**registry = git 仓库**，网站是它的只读投影

理由（都来自"部署到私有场景"这个前提）：

1. 私有环境**内网镜像一个 git 仓库**是运维的肌肉记忆（git clone --mirror），
   不需要我们自建同步协议；气隙环境用 bundle 文件摆渡。
2. append-only 审计、签名、评审（PR 即评审）、回滚（revert）全部免费获得。
3. 先不建中心服务器也能跑：任何 git 托管（含用户自己的 gitservice）都能当 registry。

### 3.2 registry 仓库结构

```
opsaxiom-registry/
  index.json                 # 生成物：全部 skill 的 id/version/maturity/域/摘要/签名者
  skills/<id>/<version>/     # skill.yaml + tests/ + attestations/（原样收录）
  keyring/
    trusted.pub              # 社区信任的签名者公钥（维护者签核后合入）
  policy.md                  # 收录政策：必须 validate 全绿 + 至少 sim_verified + 签名有效
```

### 3.3 客户端（`opsaxiom hub ...`）

- `hub search <关键词>` —— 查本地缓存的 index.json（离线可用）。
- `hub pull <id>` —— 拉取到 **`skills-community/`**（与本地 `skills/` 物理隔离，
  metadata 加 `origin: <registry-url>`），**入口三道安全门**：
  ① schema+S1-S13 全量校验（不信任远端的"已校验"声明，本地重跑）；
  ② attestation 验签 + 对照 keyring（不在 keyring → 明示 TOFU，徽章降级显示）；
  ③ maturity 徽章原样展示，**draft 拉取默认拒绝**（--allow-draft 显式放开）。
- `hub push <id>` —— 打包 skill+tests+attestations → 推分支/发 PR；
  气隙环境 `hub bundle` 产 tar，人工摆渡后 `hub import`。
- `hub sync` —— 更新 index 缓存 + 已 pull skill 的新版本提示（不自动升级，人确认）。
- **信任模型升级**：U-4 的 TOFU 是单机语义；Hub 落地后 keyring 由 registry 维护者
  签核分发，`hub sync` 同步 keyring → "签名有效"与"签名者可信"彻底分离，
  五轮评审对 U-4 的裁决即：**TOFU 作为过渡正确，终态信任锚在 registry keyring**。

### 3.4 Hub 网站 = 静态生成器（先不做动态服务）

`tools/hubsite/`：读 registry 仓库 → 纯静态 HTML（首页按域浏览 + 搜索(前端 lunr/关键词) +
Skill 详情页：决策树可视化、cautions、maturity 徽章、attestation 时间线、签名者）。
CI 在 registry 每次合入后重建。私有环境同一个生成器对内网 registry 跑一遍就是内部 Hub。
动态服务（账号/评论/API）留到社区规模需要时再上——静态站先把"可信浏览"做出来。

---

## 4. 一键部署与交互方式

### 4.1 部署（三种形态，都要求 10 分钟内可用）

| 形态 | 命令 | 场景 |
|---|---|---|
| 脚本 | `curl -fsSL .../install.sh \| bash`（或 clone 后 `./install.sh`） | 有外网/内网源 |
| 容器 | `docker run -it opsaxiom/opsaxiom` | 标准化环境 |
| 离线包 | `opsaxiom-offline.tar.gz` → `./install.sh --offline` | 气隙（核心场景！） |

install.sh 职责：装依赖（venv）、软链 `opsaxiom` 进 PATH、初始化 `~/.opsaxiom`
（密钥/会话目录）、**结束即跑 `opsaxiom doctor`**——自检依赖/权限/连接器可达性，
红黄绿输出。doctor 也是日后排障第一命令。

### 4.2 日常交互：两个入口，一条主线

**主线交互模型：symptom → diagnose → run（导航）→ attest**，全程一个终端。

- **入口 A（人找它）**：裸敲 `opsaxiom` 进入交互态——
  ```
  $ opsaxiom
  OpsAxiom> 描述你的问题：磁盘满了但 df 显示有空间
    1) [🔵] host.storage.capacity.disk-full …
  OpsAxiom> 1        ← 直接进导航档，逐步指导，结束顺手 attest
  ```
  这层只是把 diagnose/run/attest 串成会话，不引入新概念。
- **入口 B（告警找它）**：webhook 收告警 → 自动 diagnose → 把"候选 Skill + 第一步指导"
  推到 IM（钉钉/飞书卡片），人点开后回到入口 A 的流程。IM 通道是留存生命线
  （docs/01 §2），**排第七轮**，本轮先把 webhook→CLI 的接缝(`opsaxiom diagnose --json`)留好。
- **升级路径就是信任阶梯**：默认导航档；用户对某 Skill 建立信任后（自己 attest 过）
  可对该 Skill 开 copilot（只读自动跑，写操作仍简报+人执行）。档位按 Skill 记忆
  在 `~/.opsaxiom/trust.yaml`——信任是逐 Skill 积累的，不是全局开关。

### 4.3 操作手册（docs/10-user-guide.md，V 系列产出）

面向运维人员而非开发者，四章：装（三形态+doctor）、用（入口 A 全流程走一遍真例子）、
沉淀（三条捕获通道+一键认证）、交换（hub pull/push+信任徽章怎么读）。中文、带截屏式
终端输出样例，一页起步卡（cheatsheet）可打印。
