"""H-7 sec 域批量 spec（第一批）——只读安全基线审计（防御性，不含任何攻击/规避手段）。"""

_S = {"capability_level": "read", "connector": "ssh", "facts": ["os.family"]}

SPECS = [
    {**_S,
     "id": "sec.access.ssh-weak-config", "name": "SSH 弱配置审计",
     "taxonomy": "sec/access/ssh-weak-config",
     "symptom": "SSH 安全基线检查/是否允许 root 登录/是否开了密码登录/弱配置排查",
     "checks": [
        {"id": "check_rootlogin", "title": "查是否允许 root 直接登录",
         "cmd": "sshd -T 2>/dev/null | grep -ic '^permitrootlogin yes'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_root_allowed"},
                      {"when": "output.value == 0", "goto": "check_passwd"}],
         "otherwise": "check_passwd",
         "cautions": ["用 sshd -T 看'生效值'而非 grep 配置文件——Match 块/Include 会覆盖，直接读文件常误判;"
                      "PermitRootLogin yes 让 root 成暴力破解首要目标,基线应为 no 或 prohibit-password"]},
        {"id": "check_passwd", "title": "查是否允许密码登录",
         "cmd": "sshd -T 2>/dev/null | grep -ic '^passwordauthentication yes'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_passwd_on"},
                      {"when": "output.value == 0", "goto": "done_baseline_ok"}],
         "otherwise": "escalate",
         "cautions": ["开启密码登录=可被暴力破解/撞库;基线应仅用密钥(PasswordAuthentication no)。"
                      "关之前务必先确认已配好可用密钥,否则会把自己锁在外面"]},
     ],
     "dones": [
        {"id": "done_root_allowed", "summary": "允许 root 直接登录(高风险)。改 PermitRootLogin 为 no/prohibit-password,"
                                            "改用普通账号+sudo;改前确认有可用的非 root 登录方式再重载 sshd。"},
        {"id": "done_passwd_on", "summary": "root 已受限但仍允许密码登录。评估改为仅密钥认证(PasswordAuthentication no);"
                                          "先给相关账号配好密钥并验证可登录,再关闭密码认证,防止锁死。"},
        {"id": "done_baseline_ok", "summary": "SSH 基线较好(禁 root 直登+禁密码)。可进一步核对算法套件、"
                                            "登录源限制(AllowUsers/防火墙)、失败重试与 MaxAuthTries。"},
     ]},
    {**_S,
     "id": "sec.access.account-anomaly", "name": "异常账号审计",
     "taxonomy": "sec/access/account-anomaly",
     "symptom": "账号安全检查/是否有空口令账号/UID 0 非 root/可疑登录账号",
     "checks": [
        {"id": "check_uid0", "title": "查除 root 外的 UID 0 账号",
         "cmd": "awk -F: '$3==0 {c++} END{print c+0}' /etc/passwd 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1", "goto": "done_extra_root"},
                      {"when": "output.value <= 1", "goto": "check_empty"}],
         "otherwise": "check_empty",
         "cautions": ["UID 0 就是 root 权限——正常系统只应有 root 一个 UID 0;多出来的 UID 0 账号是典型的"
                      "隐蔽后门(等同于第二个 root),必须核实来历"]},
        {"id": "check_empty", "title": "查空口令可登录账号",
         "cmd": "awk -F: '($2==\"\") {c++} END{print c+0}' /etc/shadow 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_empty_pw"},
                      {"when": "output.value == 0", "goto": "done_accounts_ok"}],
         "otherwise": "escalate",
         "cautions": ["shadow 里密码字段为空=无需密码即可认证,极危险;应立即锁定(passwd -l)或设强密码。"
                      "区分'空口令'与'锁定(!/*)'——后者是正常的不可登录状态"]},
     ],
     "dones": [
        {"id": "done_extra_root", "summary": "存在非 root 的 UID 0 账号(等同隐藏 root/疑似后门)。立即核实该账号来历,"
                                          "确认非法则锁定/删除并排查入侵痕迹(登录日志/history/计划任务)。"},
        {"id": "done_empty_pw", "summary": "存在空口令可登录账号(高危)。立即 passwd -l 锁定或设强密码;"
                                        "核查该账号是否被滥用登录过,并排查是谁/何时创建的。"},
        {"id": "done_accounts_ok", "summary": "无多余 UID 0、无空口令账号。可进一步核对:新增账号、sudoers 授权范围、"
                                            "长期未用账号是否应禁用、shell 为登录 shell 的服务账号。"},
     ]},
    {**_S,
     "id": "sec.integrity.suid-anomaly", "name": "异常 SUID/SGID 文件审计",
     "taxonomy": "sec/integrity/suid-anomaly",
     "symptom": "SUID 文件检查/提权风险排查/异常 setuid 二进制",
     "checks": [
        {"id": "check_suid_count", "title": "统计系统内 SUID 文件数",
         "cmd": "find /usr /bin /sbin /opt -xdev -perm -4000 -type f 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 40", "goto": "check_writable_dirs"},
                      {"when": "output.value <= 40", "goto": "check_writable_dirs"}],
         "otherwise": "check_writable_dirs",
         "cautions": ["SUID 文件以属主权限运行,是提权的常见跳板;应与已知基线清单比对,重点看'不该有 SUID'的"
                      "程序(如 shell 解释器、find、nmap、cp)——它们带 SUID 往往是被人为植入的提权后门"]},
        {"id": "check_writable_dirs", "title": "查可疑位置(可写目录)下的 SUID 文件",
         "cmd": "find /tmp /var/tmp /dev/shm /home -xdev -perm -4000 -type f 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_suspicious_suid"},
                      {"when": "output.value == 0", "goto": "done_suid_baseline"}],
         "otherwise": "escalate",
         "cautions": ["/tmp、/home、/dev/shm 这类用户可写目录里出现 SUID 文件几乎必然是恶意的——"
                      "正常系统的 SUID 都在系统目录且属主 root,可写目录里的属高危,优先处置"]},
     ],
     "dones": [
        {"id": "done_suspicious_suid", "summary": "在用户可写目录发现 SUID 文件(高危,疑似提权后门)。隔离取证该文件"
                                               "(勿直接删,先留证),核实哈希/来历,清除并排查入侵链(是谁放的、怎么进来的)。"},
        {"id": "done_suid_baseline", "summary": "可写目录无异常 SUID。将系统目录 SUID 清单与基线比对,重点核对非标准程序;"
                                             "建立 SUID 基线并定期 diff,新增项及时审查。"},
     ]},
    {**_S,
     "id": "sec.network.unexpected-listen", "name": "异常监听端口审计",
     "taxonomy": "sec/network/unexpected-listen",
     "symptom": "监听端口检查/是否有未预期服务对外监听/可疑端口",
     "checks": [
        {"id": "check_listen", "title": "统计对外(非本地回环)监听端口数",
         "cmd": "ss -ltnH 2>/dev/null | awk '{print $4}' | grep -vcE '127\\.0\\.0\\.1|::1|\\[::1\\]'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_high_ports"},
                      {"when": "output.value == 0", "goto": "done_only_local"}],
         "otherwise": "check_high_ports",
         "cautions": ["监听 0.0.0.0/:: 才是对外暴露,只听 127.0.0.1 的服务不对外;审计时先把回环的排除,"
                      "剩下的每个对外端口都要能对应到一个已知服务"]},
        {"id": "check_high_ports", "title": "查高位端口上的可疑监听",
         "cmd": "ss -ltnpH 2>/dev/null | awk '{split($4,a,\":\"); p=a[length(a)]; if(p+0>1024 && $4!~/127.0.0.1|::1/) c++} END{print c+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_high_listen"},
                      {"when": "output.value == 0", "goto": "done_listen_known"}],
         "otherwise": "escalate",
         "cautions": ["高位端口对外监听不一定是坏事(很多正常服务用高位),但要能说清是哪个进程/服务;"
                      "对不上进程、或进程名可疑(乱码/隐藏路径)的高位监听,是反连木马/后门的特征"]},
     ],
     "dones": [
        {"id": "done_only_local", "summary": "仅本地回环监听,无对外暴露。基线良好;若预期应有对外服务却没有,反查服务是否没起。"},
        {"id": "done_high_listen", "summary": "存在对外的高位端口监听。逐一用 ss -ltnp 对应进程,确认每个都是已知服务;"
                                           "对不上进程或进程可疑的,取证排查是否为后门/反连木马。"},
        {"id": "done_listen_known", "summary": "对外监听均在常规端口。仍应逐一核对进程与预期一致,并用防火墙收窄"
                                            "对外暴露面(只放行必要端口+来源)。"},
     ]},
    {**_S,
     "id": "sec.audit.auditd-gap", "name": "auditd 审计日志断档排查",
     "taxonomy": "sec/audit/auditd-gap",
     "symptom": "审计日志断档/auditd 没运行/审计记录丢失/合规要求审计连续",
     "checks": [
        {"id": "check_running", "title": "查 auditd 是否在运行",
         "cmd": "systemctl is-active auditd 2>/dev/null | grep -ic '^active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_not_running"},
                      {"when": "output.value > 0", "goto": "check_lost"}],
         "otherwise": "check_lost",
         "cautions": ["auditd 没运行=这段时间完全没有审计记录,合规和事后取证都断档;"
                      "先确认服务状态,别默认'装了就一定在跑'"]},
        {"id": "check_lost", "title": "查审计事件是否有丢弃(缓冲不足)",
         "cmd": "auditctl -s 2>/dev/null | awk '/^lost/{print \"lost\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.lost > 0", "goto": "done_events_lost"},
                      {"when": "output.lost == 0", "goto": "done_audit_ok"}],
         "otherwise": "escalate",
         "cautions": ["lost 计数增长=审计事件产生太快、缓冲(backlog)装不下被丢——审计有洞;"
                      "调大 -b backlog_limit,或收窄规则减少无关事件"]},
     ],
     "dones": [
        {"id": "done_not_running", "summary": "auditd 未运行,审计断档。启动并设开机自启(systemctl enable --now auditd);"
                                           "排查它为何停(被关/崩溃/磁盘满),补齐关键审计规则。"},
        {"id": "done_events_lost", "summary": "auditd 在跑但有事件丢弃(lost>0)。调大 backlog_limit(-b)、"
                                           "精简过泛的审计规则减少无关事件;确认审计日志盘没满导致写不进。"},
        {"id": "done_audit_ok", "summary": "auditd 运行正常且无丢弃。核对审计规则是否覆盖关键点(登录、提权、"
                                         "敏感文件、账号变更),并确认日志轮转与留存满足合规要求。"},
     ]},
]
