# 社区发布流程实战走查（G-6）

> 目标：以"装了客户端的社区用户"视角，完整走一遍 **验证 → 签名 → 打包 → PR → CI → 合入 → 上架**，
> 供项目发起人评估 GitHub PR 机制是否合理。本文所有终端输出均为真实执行捕获（2026-07-14）。
> 分工：能自动的已自动（含用纯 Python `tools/gitpush.py` 推送）；**PR 的创建与合并留给发起人在网页操作**
> ——因为这正是要评估的环节。

## 0. 角色与前置

- 角色：社区贡献者，已装 OpsAxiom 客户端，SSH 公钥已加到 GitHub。
- 待投稿 Skill：`host.cpu.throttled`（G-1，本轮新写，已 sim_verified）。
- 社区 registry：https://github.com/hf4Academic/opsaxiom-registry

## 1. 新用户零配置接入并拉一个已有 Skill（三道安全门）

```
$ opsaxiom hub pull host.storage.capacity.disk-full
（首次使用：自动接入官方社区 https://github.com/hf4Academic/opsaxiom-registry.git）
✔ 已拉取到 skills-community/host-storage-capacity-disk-full
  门①校验：0 ERROR  门②验签：… 门③徽章：sim_verified
```

要点：无需先记 `hub init` 的长地址——未配置时自动接入官方社区；拉取永远**本地重跑校验**
（不信远端"已校验"声明），这是社区可信的底线。

## 2. 验证待投稿的新 Skill（导航档实跑）

```
$ opsaxiom run host.cpu.throttled --answers demos/cpu-throttled-guided.answers.yaml
OpsAxiom · 容器/cgroup CPU 限流排查  [🔵sim]  模式=guided
━━ [排查] 确认是否发生 CPU 限流及其强度 ━━
  ⚠ cgroup v1/v2 文件路径不同…
▶ 请执行并粘贴输出（END 结束）：
  $ cat /sys/fs/cgroup/cpu.stat 2>/dev/null || cat /sys/fs/cgroup/cpu/cpu.stat
→ 判读结果：转 check_quota
━━ [排查] 读取 CPU 配额以量化缺口 ━━
→ 判读结果：转 done_severe
━━ ✅ 结论 ━━
严重限流…当前配额约 1.5 核，明显不足。处置：K8s 调 limit（不要直接改 cgroup）…
```

判读逐步验证到 `done_severe`，结论正确——用户确认这个 Skill 在自己环境好用。

## 3. 一键签名 attestation（把"我验证过"沉淀成社区凭据）

```
$ opsaxiom-attest --skill host.cpu.throttled --skill-version 0.1.0 \
    --outcome resolved --mode navigator --os-family debian --scale 30 --attestor gh:hf4Academic
已生成 attestation: skills/host/cpu/throttled/attestations/2026-07-14-xxxxxxxx.yaml
提示：env_fingerprint 只含分桶信息，无标识性数据。已 ed25519 签名。
```

env_fingerprint 只落**分桶**（debian / 10-100 台），不含主机名/IP（R11）。

## 4. 打包并推 submit 分支（终端自动，PR 留给你）

```
$ opsaxiom hub push host.cpu.throttled
已打包：~/.opsaxiom/hub/outbox/host.cpu.throttled.tar.gz

# 把 bundle 解到 registry 克隆的 skills/<id>/<version>/，建分支并推送：
$ python tools/gitpush.py ~/.opsaxiom/hub/registry \
    git@github.com:hf4Academic/opsaxiom-registry.git \
    refs/heads/submit/host-cpu-throttled:refs/heads/submit/host-cpu-throttled
✔ 已推送 …（submit/host-cpu-throttled）
```

分支 `submit/host-cpu-throttled` 已在 GitHub。

### 👉 发起人操作①：开 PR（评估这一步的体验）

打开 https://github.com/hf4Academic/opsaxiom-registry —— GitHub 会在首页横幅提示
**"Compare & pull request"**，点开即是发布表单：
- 标题/正文写你在什么环境验证过（PR 正文就是"投稿说明"）；
- "Files changed" 只应显示新增 `skills/host.cpu.throttled/0.1.0/`（skill.yaml + attestations + .maturity）。
- 直接开 PR，或对比 `submit/host-cpu-throttled` → `main`。

**评估点**：这一步是否比"网页上传"更顺？PR 正文能否承载足够的投稿信息？

## 5. CI 自动质检（PR 上自动跑）

PR 一开，`.github/workflows/validate.yml` 自动触发：
- `validate` job：对新增 skill 重跑结构+语义 S1–S13+语法树校验；
- draft 拒收检查（本 Skill 是 sim_verified，应放行）。

Actions 结果在 PR 页面 "Checks" 区。**评估点**：CI 反馈是否清晰、够不够快、绿了才能合是否合理。

## 6. 合入与上架

### 👉 发起人操作②：Review 并 Merge

CI 绿后在 PR 页 review → Merge。合入 `main` 触发 `rebuild-index` job：
机器人重跑 `build_registry` 更新 `index.json` 并提交（"合入即上架"）。

### 合入后验证（这些可自动/由你复核）

```
$ opsaxiom hub sync                    # 拉最新 index + keyring
$ opsaxiom hub search 限流              # 应能搜到 host.cpu.throttled
$ opsaxiom hub pull host.cpu.throttled # 三道门通过，拉到本地
# 网站重建：python tools/hubsite/build.py <registry> <site> && gitpush 推 opsaxiom-site
#   → https://hf4academic.github.io/opsaxiom-site 出现新 Skill
```

## 附：哪步是人、哪步是自动（诚实边界）

| 步骤 | 谁做 | 说明 |
|---|---|---|
| 1 拉取/验证/签名/打包 | 自动（客户端） | 本文已真实执行捕获 |
| 4 推 submit 分支 | 自动（gitpush.py） | 已推，分支在 GitHub |
| **开 PR** | **发起人（网页）** | 要评估的环节；API 建 PR 需 token |
| 5 CI 质检 | 自动（GitHub Actions） | PR 触发 |
| **Merge** | **发起人（网页）** | 合入是治理动作，人来背书 |
| 6 索引重建 | 自动（CI 机器人） | 合入即上架 |
| 网站重建 | 半自动 | build + gitpush（可后续做成 Pages CI） |
