# OpsAxiom 用户手册（面向运维人员）

> 这份手册给**用它的运维人员**，不是给开发者。四章：装 → 用 → 沉淀 → 交换。
> 一句话理解 OpsAxiom：**它不替你乱按，它像个懂行的老师傅站你旁边，一步步告诉你查什么、
> 注意什么，命令你自己敲；等你信得过某个流程了，再让它多担一点。**

---

## 一页起步卡（可打印）

```
装      ./install.sh            # 完事自动体检；docker run opsaxiom 也行
体检    opsaxiom doctor         # 红=必修 黄=可用但受限
找      opsaxiom diagnose "磁盘满了但df有空间"
查      opsaxiom run <skill-id> # 逐步指导，你敲命令，它判读放行
        run 中变更步骤：确认/跳过/升级人工/退出(可 --resume 续)
沉淀    排查完顺手答一句认证；没走skill就 record；老经验用 skill new
拿      opsaxiom hub search 磁盘 ; opsaxiom hub pull <id>
发      opsaxiom hub push <id>
```

---

## 第一章 · 装（10 分钟内可用）

三种形态，任选：

| 形态 | 命令 | 适合 |
|---|---|---|
| 脚本 | `./install.sh`（内网/有源） | 大多数机器 |
| 容器 | `docker run -it opsaxiom` | 标准化环境 |
| 离线 | 解开 `opsaxiom-offline.tar.gz` → `./install.sh --offline` | **气隙内网** |

装完会自动跑一次 **`opsaxiom doctor`**：

- 🟢 全绿 → 直接用。
- 🟡 黄 → 能用，只是某些域的"真实执行"或签名功能受限（例如没装 kubectl，k8s 域的
  `--real` 自动执行用不了，但**导航档指导照常**）。
- 🔴 红 → 必须先修（缺 python 依赖 / 目录没权限），doctor 会写清怎么修。

日后任何"怎么跑不起来"，第一件事都是 `opsaxiom doctor`。

---

## 第二章 · 用（一次完整排查长什么样）

### 主线：说问题 → 找 Skill → 跟着查 → 顺手认证

**1) 描述问题，让它找对应的排查流程（Skill）：**

```
$ opsaxiom diagnose "磁盘满了但 df 显示还有空间"
  1) [🔵sim] host.storage.capacity.disk-full —— 磁盘空间耗尽排查与处置
  2) ...
```

徽章表示这个 Skill 被验证到什么程度：⚪草稿 · 🔵仿真验证 · 🟢实地验证 · 🟡官方认证。
优先选徽章高的。

**2) 跟着它一步步查：**

```
$ opsaxiom run host.storage.capacity.disk-full
━━ [排查] 定位是哪个挂载点满了 ━━
  ⚠ df 有空间却报 No space：多半是 inode 耗尽，别只看容量
▶ 请执行并粘贴输出（END 结束）：
  $ df -B1 --output=target,size,used,avail,pcent /
（你在自己的终端敲这条命令，把输出粘回来）
→ 判读结果：转 check_inode
```

它**只出方案和判读，命令你自己敲**——这是"导航档"，最安全的默认档位。

**3) 遇到要改动的步骤（变更），它先给你一份"变更简报"再等你拍板：**

```
━━ [变更] 压缩 7 天前的历史日志 ━━  风险: low
📋 变更简报
  影响面: 只动 /var/log 下 7 天前的 .log
  执行中盯: df 使用率应下降
  什么情况立即中止: 磁盘不降反升
  ── 将要执行的命令（请你亲自执行，Agent 不代执行）──
    $ find /var/log -name '*.log' -mtime +7 -exec gzip {} \;
  ── 回滚方案 ──
    $ gunzip /var/log/*.log.gz
需要审批。你的决定？
  1) 确认，我亲自执行  2) 跳过此步  3) 升级人工  4) 退出会话
```

写操作**永远由你亲手执行**，它不代按。选 4 退出后，`opsaxiom run <id> --sid <会话> --resume`
可从中断处接着来。

**4) 查完，顺手把这次经历沉淀下来（见第三章）。**

### 另一个入口：告警自动触发（可选）
接了 IM（钉钉/飞书）后，告警来了会自动 diagnose，把"候选 Skill + 第一步"推到群里，
你点开就回到上面的流程。

### 信任是逐个 Skill 攒出来的
默认所有 Skill 都走导航档。等你亲手验证过某个 Skill 几次、信得过了，可以对**那一个**
开更省事的档位（只读命令自动跑，写操作仍要你确认）。信任不是一个全局开关，是一格一格加的。

---

## 第三章 · 沉淀（把你的经验变成 Skill）

三条路，按省力程度排：

**A. 排查完顺手认证（最省力）** —— 你刚用 `opsaxiom run` 查完一个真问题，结尾它会问：
> 要把这次验证沉淀为社区凭据吗？[y/N]

答 y，再补两个不敏感的信息（什么系统、大概多少台机器），30 秒生成一份**带签名**的验证记录。
这份记录是这个 Skill "在真实环境被验证过"的证据——攒够了它的徽章就升级。
（补交：`opsaxiom attest --from-session <会话号>`。）

**B. 排查没用到现成 Skill？边查边录** ——
```
opsaxiom record start 我的排查
opsaxiom record exec "df -h /"      # 代你跑只读命令并留痕（写操作会被拒绝）
opsaxiom record stop
opsaxiom skill from-session rec-我的排查 --id host.xxx.yyy --name "..." --taxonomy host/xxx/yyy
```
它把你这趟排查回放成一个 Skill 草稿：命令、输出样例都在，你只要补上"每步在判断什么、
每种情况怎么办、有什么坑"。

**C. 脑子里的老经验，问答倒出来** —— `opsaxiom skill new`，它一句句问，你一句句答，问完出草稿。

三条路产出的都是**草稿**。补完后跑 `opsaxiom skill lint <草稿>`，它列出还差什么
（哪个判据没填、哪条 caution 是占位、缺不缺回滚）。补齐 → 写个测试场景 → 验证通过就自动升级。
**降低的是写的麻烦，不降质量门槛**——这是别人敢用你 Skill 的底线。

---

## 第四章 · 交换（和社区互通有无）

Skills Hub 就是一个 git 仓库（内网可镜像、气隙可用 bundle 摆渡）。

**拿别人的：**
```
opsaxiom hub init <registry地址>          # 一次性配置
opsaxiom hub search 暴力破解
opsaxiom hub pull sec.access.bruteforce   # 拉下来
```
拉取时会自动过三道关，你会看到结果：
- **门①校验**：在你本地重新校验一遍（不信对方一面之词）；
- **门②验签**：这份 Skill 的实地验证记录签名对不对、签名者你信不信任
  （不在你的信任名单里会标 `TOFU`——能用，但用于自动化前自己掂量）；
- **门③徽章**：草稿默认不给拉（`--allow-draft` 才放开）。

拉来的放在 `skills-community/`，和你自己的 `skills/` 分开，互不污染。

**发自己的：**
```
opsaxiom hub push <你的skill-id>          # 打成 bundle
```
把 bundle 摆渡到 registry 侧导入，或走 git PR。你的 Skill 连同签名的验证记录一起走。

**浏览（网页版）：** 对 registry 跑一遍站点生成器就得到一个内部 Hub 网站——
按域浏览、搜索、点开看决策树和谁在什么环境验证过。私有环境完全离线可用。

---

## 常见问题

- **它会不会自己乱改我系统？** 不会。默认导航档下写操作一律你亲手执行，它只给方案和回滚。
- **回滚是不是每步都有？** 是。可回滚是本项目第一准则——任何变更步骤都配回滚方案，没有就不该出这一步。
- **凭据/密码会被上传吗？** 不会。验证记录只含分桶信息（"rhel 8.x / 10-100 台"这种），
  绝不含主机名/IP/密码；记录本地签名，你决定推不推。
- **跑不起来？** `opsaxiom doctor`。
