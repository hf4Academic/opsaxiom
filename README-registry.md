# 搭建你自己的 Skills 社区（registry + 网站）

> 回答三个问题：社区是什么形态？怎么从零搭起来？别人怎么发布？
> 设计依据 docs/08 §3：**registry = 一个 git 仓库（GitHub 即可），网站是它的只读投影。**
> 不需要自建服务器——审计、签名、评审（PR 即评审）、回滚（revert）全部由 git 免费提供。

## 一、形态：GitHub 仓库 + GitHub Pages 静态站

```
GitHub 仓库 opsaxiom-registry/        ← 社区的“数据库”（唯一事实来源）
  index.json                           全部 Skill 的索引（CI 自动重建）
  skills/<id>/<version>/               skill.yaml + tests + attestations
  keyring/trusted.pub                  可信签名者公钥（维护者签核合入）
  policy.md                            收录政策：校验全绿 + ≥sim_verified + 签名有效

GitHub Pages（同仓库或独立仓库）       ← 社区的“门面”（只读浏览）
  由 tools/hubsite/build.py 生成：域浏览 / 搜索 / 决策树可视化 / 认证记录
```

## 二、从零搭建（约 10 分钟）

**1) 生成 registry 内容**（用本仓库 73 个 Skill 起步）：

```bash
opsaxiom hub build-registry skills /tmp/opsaxiom-registry
```

**2) 推成 GitHub 仓库**：

```bash
cd /tmp/opsaxiom-registry
git init && git add -A && git commit -m "OpsAxiom registry 首发（73 Skill）"
# 在 GitHub 上新建空仓库 opsaxiom-registry，然后：
git remote add origin git@github.com:<你>/opsaxiom-registry.git
git push -u origin main
```

**3) 生成并发布网站**（GitHub Pages）：

```bash
python tools/hubsite/build.py /tmp/opsaxiom-registry /tmp/opsaxiom-site
cd /tmp/opsaxiom-site
git init && git add -A && git commit -m "hub site"
git remote add origin git@github.com:<你>/opsaxiom-site.git
git push -u origin main
# GitHub 仓库 Settings → Pages → Deploy from branch(main / root)
# 几分钟后 https://<你>.github.io/opsaxiom-site 就是社区网站
```

**4) 配 CI 自动重建**（可选但推荐）：registry 仓库加一个 workflow——
每次合入 PR 后重跑 `validate` + 重建 `index.json` + 重建静态站推到 Pages。
这样"合入即上架"。

**5) 用户端接入**：

```bash
opsaxiom hub init https://github.com/<你>/opsaxiom-registry.git
opsaxiom hub sync            # 拉索引 + keyring
opsaxiom hub search 磁盘      # 离线搜索
opsaxiom hub pull <skill-id> # 三道安全门：本地重跑校验 / 验签 / draft 拒收
```

## 三、发布的两条通道（你理解得对）

**终端发布（主通道，pi 里 /publish 或命令行）**：

```bash
opsaxiom hub push <skill-id>
# → 打包 ~/.opsaxiom/hub/outbox/<id>.tar.gz（skill+tests+attestations+签名）
# → 到 registry 仓库：解包进 skills/<id>/<version>/ → git 提 PR
# 气隙环境：bundle 文件人工摆渡，registry 侧 `hub import`
```

**网页发布（GitHub 网页就是发布页面）**：
fork registry 仓库 → 网页上传 skill 目录 → 发 PR。
**不需要自建"上传网站"**——PR 页面天然就是：表单（描述）+ 评审（维护者）+
CI 质检（validate 全绿才能合）+ 留痕（讨论记录）。docs/08 §3.4 的裁决就是
"动态服务（账号/评论/API）留到社区规模需要时再上"。

**收录质量门（两条通道都一样，policy.md + CI 强制）**：
- `python tools/validate.py` 全绿（结构 + 语义 S1–S13 + 命令语法树）
- maturity ≥ sim_verified（⚪draft 默认拒收）
- attestation 签名验签有效；签名者进 keyring 需维护者双人复核（docs/08 §3.3a）

## 四、信任与治理（社区可信的底线）

- **签名**：每份实地验证（attestation）都是 Ed25519 签名的，谁验证的可追溯。
- **keyring**：`keyring/trusted.pub` 是"谁可信"的治理载体，加人走 PR 双人复核。
- **三道安全门在用户侧**：pull 下来永远本地重跑校验——不信任远端的"已校验"声明。
