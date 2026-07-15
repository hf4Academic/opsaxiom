"""H-7 sec 域批量 spec（第二批）——只读安全基线审计（防御性）。"""

_S = {"capability_level": "read", "connector": "ssh", "facts": ["os.family"]}

SPECS = [
    {**_S,
     "id": "sec.network.abnormal-outbound", "name": "异常外连排查",
     "taxonomy": "sec/network/abnormal-outbound",
     "symptom": "可疑出站连接/机器主动外连陌生地址/疑似反连木马或挖矿外联",
     "checks": [
        {"id": "check_estab", "title": "统计对外已建立连接数",
         "cmd": "ss -tnH state established 2>/dev/null | awk '{print $4}' | grep -vcE '127\\.0\\.0\\.1|::1'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_proc"},
                      {"when": "output.value == 0", "goto": "done_no_outbound"}],
         "otherwise": "check_proc",
         "cautions": ["排查外连先看'谁在连、连去哪'两件事;正常业务外连能对应到已知服务(DB/API/仓库),"
                      "对不上进程或目的地陌生的才可疑,别把正常业务连接当威胁"]},
        {"id": "check_proc", "title": "查是否有无属主/可疑进程发起外连",
         "cmd": "ss -tnpH state established 2>/dev/null | grep -icE 'users:\\(\\(\"(sh|bash|perl|python[0-9.]*|nc|ncat|curl|wget)\"'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_suspicious_conn"},
                      {"when": "output.value == 0", "goto": "done_outbound_known"}],
         "otherwise": "escalate",
         "cautions": ["shell/脚本解释器/nc 直接持有对外长连接是反连(reverse shell)的典型特征;"
                      "而 curl/wget 常连=可能是定时下载器(挖矿/木马拉马)。看它连的目的地和父进程链"]},
     ],
     "dones": [
        {"id": "done_no_outbound", "summary": "无对外已建立连接。若怀疑外连威胁,可再抓一段时间(周期性外连可能间歇);"
                                           "或结合防火墙出站日志看有无被拦的尝试。"},
        {"id": "done_suspicious_conn", "summary": "shell/脚本/nc 类进程持有外连(疑似反连或恶意下载)。取证(记录目的IP/端口/"
                                               "进程树/打开文件),隔离该主机,排查入侵入口与持久化(计划任务/启动项)。"},
        {"id": "done_outbound_known", "summary": "外连均由常规服务发起。逐一核对目的地与业务预期一致,"
                                               "用出站防火墙白名单收窄(只放行必要目的地),降低被反连/外传的面。"},
     ]},
    {**_S,
     "id": "sec.access.fail2ban-ineffective", "name": "fail2ban 失效排查(暴力破解未被拦)",
     "taxonomy": "sec/access/fail2ban-ineffective",
     "symptom": "大量失败登录却没被封/fail2ban 装了不生效/暴力破解没拦住",
     "checks": [
        {"id": "check_running", "title": "查 fail2ban 是否在运行",
         "cmd": "systemctl is-active fail2ban 2>/dev/null | grep -ic '^active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_not_running"},
                      {"when": "output.value > 0", "goto": "check_jail"}],
         "otherwise": "check_jail",
         "cautions": ["'装了但没在跑'是最常见失效——先确认服务 active,别默认它一直在守"]},
        {"id": "check_jail", "title": "查 sshd jail 是否启用且有拦截",
         "cmd": "fail2ban-client status sshd 2>/dev/null | awk '/Currently banned/{print \"banned\", $NF}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.banned >= 0", "goto": "done_jail_active"}],
         "otherwise": "done_jail_missing",
         "cautions": ["能查到 sshd jail 状态=jail 已启用;查不到(命令失败)多为没 enable sshd jail 或日志路径/backend"
                      "配错,导致 fail2ban 根本没在读认证日志、看不到失败登录"]},
     ],
     "dones": [
        {"id": "done_not_running", "summary": "fail2ban 未运行,暴破无人拦。systemctl enable --now fail2ban 启动并自启;"
                                           "排查它为何停,确认 jail.local 配置正确后再观察拦截。"},
        {"id": "done_jail_active", "summary": "sshd jail 已启用在工作。若仍觉没拦住,核对 maxretry/findtime/bantime"
                                           "是否太宽松、日志路径是否匹配当前系统(journald vs 文件),必要时收紧阈值。"},
        {"id": "done_jail_missing", "summary": "服务在跑但 sshd jail 没生效(查不到状态)。检查 jail.local 是否 enabled=true、"
                                             "logpath/backend 是否匹配本机认证日志来源;修正后重载并验证能读到失败登录。"},
     ]},
    {**_S,
     "id": "sec.tls.cert-expiry", "name": "TLS 证书临期/链路问题排查",
     "taxonomy": "sec/tls/cert-expiry",
     "symptom": "证书快过期/HTTPS 报证书错误/证书链不全/浏览器告警不受信",
     "params": {"endpoint": "待检测的 host:port，如 example.com:443"},
     "checks": [
        {"id": "check_days", "title": "查证书剩余有效天数",
         "cmd": "echo | openssl s_client -connect {{endpoint}} -servername ${SNI:-localhost} 2>/dev/null | openssl x509 -noout -checkend 604800 2>/dev/null; echo $?",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_chain"},
                      {"when": "output.value == 0", "goto": "check_chain"}],
         "otherwise": "check_chain",
         "cautions": ["checkend 604800 判断'是否 7 天内过期',返回非 0 即将过期;证书过期是最高频的可用性事故之一,"
                      "应提前(30 天)告警而非等浏览器报错"]},
        {"id": "check_chain", "title": "查证书链是否完整可信",
         "cmd": "echo | openssl s_client -connect {{endpoint}} -servername ${SNI:-localhost} 2>&1 | grep -icE 'unable to get local issuer|self signed|verify error|certificate has expired'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_chain_broken"},
                      {"when": "output.value == 0", "goto": "done_cert_ok"}],
         "otherwise": "escalate",
         "cautions": ["'unable to get local issuer'=服务器没把中间证书一起发下来(链不全)——本机 curl 可能因缓存"
                      "中间证而正常,别的客户端却报错;必须在服务端补全证书链(fullchain)"]},
     ],
     "dones": [
        {"id": "done_chain_broken", "summary": "证书链不完整或不受信(缺中间证/自签/已过期)。服务端部署 fullchain(叶证+中间证),"
                                            "确认用了受信 CA;自签证书需在客户端信任或换正式证书。"},
        {"id": "done_cert_ok", "summary": "证书链完整且短期内不过期。纳入到期巡检(提前 30 天告警)、确认自动续期"
                                        "(如 certbot)在跑,避免下次临期无人续。"},
     ]},
    {**_S,
     "id": "sec.integrity.world-writable", "name": "关键路径权限过松审计",
     "taxonomy": "sec/integrity/world-writable",
     "symptom": "文件权限过松/world-writable 敏感文件/配置可被任意用户改",
     "checks": [
        {"id": "check_ww_bin", "title": "查系统目录下的 world-writable 文件",
         "cmd": "find /etc /usr/bin /usr/sbin /bin /sbin -xdev -type f -perm -0002 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_ww_system"},
                      {"when": "output.value == 0", "goto": "check_ww_noexec"}],
         "otherwise": "check_ww_noexec",
         "cautions": ["系统目录里任何 world-writable 文件都是高危——任意用户可改 /etc 配置或系统二进制=提权/持久化;"
                      "正常系统这里应为 0 个"]},
        {"id": "check_ww_noexec", "title": "查关键配置的 world-writable 情况",
         "cmd": "find /etc/cron.d /etc/cron.daily /etc/systemd/system -xdev -type f -perm -0002 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_ww_cron"},
                      {"when": "output.value == 0", "goto": "done_perms_ok"}],
         "otherwise": "escalate",
         "cautions": ["cron/systemd 目录 world-writable 尤其危险——普通用户可写入定时任务/服务单元实现 root 提权;"
                      "这类是攻击者最爱的持久化落点"]},
     ],
     "dones": [
        {"id": "done_ww_system", "summary": "系统目录存在 world-writable 文件(高危)。立即收紧权限(chmod o-w),"
                                         "核实是谁/何时改松的、是否已被利用(查文件内容/修改时间/相关日志)。"},
        {"id": "done_ww_cron", "summary": "cron/systemd 配置目录有 world-writable 项(可被提权持久化)。立即 chmod o-w,"
                                       "逐一核对这些任务/单元内容是否被篡改或植入,清除可疑项。"},
        {"id": "done_perms_ok", "summary": "关键路径无 world-writable。可进一步核对敏感文件属主与权限"
                                         "(/etc/shadow 600、私钥 600、sudoers 440),建立权限基线定期核查。"},
     ]},
    {**_S,
     "id": "sec.kernel.security-baseline", "name": "内核安全基线审计",
     "taxonomy": "sec/kernel/security-baseline",
     "symptom": "内核安全基线检查/ASLR 是否开/内核参数加固/合规基线核对",
     "checks": [
        {"id": "check_aslr", "title": "查 ASLR 是否启用",
         "cmd": "cat /proc/sys/kernel/randomize_va_space 2>/dev/null | awk '{print \"aslr\", $1}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.aslr < 2", "goto": "done_aslr_off"},
                      {"when": "output.aslr >= 2", "goto": "check_dmesg"}],
         "otherwise": "check_dmesg",
         "cautions": ["randomize_va_space 应为 2(完全 ASLR);被调成 0/1 会大幅削弱对内存破坏类漏洞的防护——"
                      "有人为调试关了 ASLR 后忘了恢复是常见基线偏移"]},
        {"id": "check_dmesg", "title": "查非特权用户是否可读内核日志",
         "cmd": "cat /proc/sys/kernel/dmesg_restrict 2>/dev/null | awk '{print \"restrict\", $1}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.restrict == 0", "goto": "done_dmesg_open"},
                      {"when": "output.restrict > 0", "goto": "done_baseline_ok"}],
         "otherwise": "escalate",
         "cautions": ["dmesg_restrict=0 让普通用户能读内核日志,可能泄露内核地址/指针帮助绕过 ASLR;"
                      "加固基线应设为 1。这类 sysctl 项要写进 /etc/sysctl.d 持久化,别只临时改"]},
     ],
     "dones": [
        {"id": "done_aslr_off", "summary": "ASLR 未完全启用(<2)。设 kernel.randomize_va_space=2 并写入 sysctl.d 持久化;"
                                         "排查是否有调试脚本/配置把它关了。"},
        {"id": "done_dmesg_open", "summary": "内核日志对普通用户开放(dmesg_restrict=0)。设为 1 限制读取并持久化;"
                                          "顺带核对其它加固项(kptr_restrict、ptrace_scope、sysrq)。"},
        {"id": "done_baseline_ok", "summary": "ASLR 与 dmesg 限制均达标。可继续核对更多加固项(kptr_restrict、"
                                            "kernel.yama.ptrace_scope、net.ipv4 反欺骗),并确保都在 sysctl.d 持久化。"},
     ]},
]
