"""H-2 host 域批量 spec（第一批）。领域内容 Opus 按运维知识填，生成器编译+求解+晋级。"""

SPECS = [
    {
        "id": "host.system.cron-not-firing", "name": "cron 定时任务没跑排查",
        "taxonomy": "host/system/cron-not-firing",
        "symptom": "定时任务没执行/crontab 写了不生效/脚本该跑没跑",
        "checks": [
            {"id": "check_daemon", "title": "确认 cron 服务在运行",
             "cmd": "systemctl is-active cron crond 2>/dev/null | grep -c active",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value == 0", "goto": "done_daemon_down"},
                          {"when": "output.value > 0", "goto": "check_logs"}],
             "otherwise": "check_logs",
             "cautions": ["Debian 系服务名是 cron，RHEL 系是 crond，两个都查"]},
            {"id": "check_logs", "title": "查最近是否有该任务的执行记录",
             "cmd": "journalctl -u cron -u crond --since '-1h' 2>/dev/null | grep -c CRON",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value == 0", "goto": "done_not_scheduled"},
                          {"when": "output.value > 0", "goto": "done_ran_check_script"}],
             "otherwise": "escalate",
             "cautions": ["cron 环境变量极简（无 PATH/无 shell profile），脚本里用绝对路径，"
                          "别假设有交互 shell 的环境；输出重定向了才看得到报错"]},
        ],
        "dones": [
            {"id": "done_daemon_down", "summary": "cron 服务没运行——任务当然不跑。启动并设开机自启："
                                                  "systemctl enable --now cron（或 crond）。"},
            {"id": "done_not_scheduled", "summary": "近 1 小时无该任务执行记录。核对：①crontab 语法"
                                                    "（分 时 日 月 周，5 段）；②是不是写在了别的用户的 crontab 下；"
                                                    "③文件末尾要有换行，否则最后一行不生效。"},
            {"id": "done_ran_check_script", "summary": "cron 有拉起任务，问题在脚本本身。把命令改成 "
                                                       "'bash -lc \"你的命令\" >>/tmp/cron.log 2>&1' 捕获输出，"
                                                       "多半是 PATH 或权限问题。"},
        ],
    },
    {
        "id": "host.system.ntp-unsynced", "name": "NTP 未同步排查（chrony/ntpd）",
        "taxonomy": "host/system/ntp-unsynced",
        "symptom": "时间不同步/chrony 不 sync/时间源不可达",
        "checks": [
            {"id": "check_service", "title": "确认时间同步服务在跑",
             "cmd": "systemctl is-active chronyd ntpd systemd-timesyncd 2>/dev/null | grep -c active",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value == 0", "goto": "done_no_service"},
                          {"when": "output.value > 0", "goto": "check_sources"}],
             "otherwise": "check_sources",
             "cautions": ["三选一，别同时装两个（会抢 UDP 123 互相打架）"]},
            {"id": "check_sources", "title": "查时间源可达性",
             "cmd": "chronyc sources 2>/dev/null | grep -c '^\\^\\*'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value == 0", "goto": "done_no_reachable_source"},
                          {"when": "output.value > 0", "goto": "done_synced"}],
             "otherwise": "escalate",
             "cautions": ["'^*' 才是当前选定的同步源；只有 '^?' 说明源都不可达，多为 UDP 123 被防火墙挡"]},
        ],
        "dones": [
            {"id": "done_no_service", "summary": "没有时间同步服务在运行。装并启用 chrony："
                                                 "systemctl enable --now chronyd。"},
            {"id": "done_no_reachable_source", "summary": "没有可达的时间源。检查 ①出方向 UDP 123 是否放行；"
                                                          "②chrony.conf 里的 server/pool 地址是否可解析可达；"
                                                          "内网环境需指向内网 NTP。"},
            {"id": "done_synced", "summary": "时间源已选定且在同步。若仍报时间不对，看偏移是否在收敛"
                                             "（chronyc tracking 的 System time），大偏移会缓慢步进对齐。"},
        ],
    },
    {
        "id": "host.process.thread-explosion", "name": "线程数暴涨排查",
        "taxonomy": "host/process/thread-explosion",
        "symptom": "线程数暴涨/pthread_create 失败/Resource temporarily unavailable",
        "checks": [
            {"id": "count_threads", "title": "统计系统线程总数与上限",
             "cmd": "echo \"used $(ps -eLf | wc -l) max $(cat /proc/sys/kernel/threads-max)\"",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.used > 30000", "goto": "find_culprit"},
                          {"when": "output.used <= 30000", "goto": "done_not_high"}],
             "otherwise": "find_culprit",
             "cautions": ["线程也占 PID，可能先撞 pid_max 而非 threads-max；两个上限都要看"]},
            {"id": "find_culprit", "title": "找线程最多的进程",
             "cmd": "ps -eLf | awk '{print $2}' | sort | uniq -c | sort -rn | head -5",
             "parser": "generic/table-v1",
             "branches": [{"when": "rows[0].name > 1000", "goto": "done_single_culprit"},
                          {"when": "output.row_count > 0", "goto": "done_spread"}],
             "otherwise": "escalate",
             "cautions": ["单进程线程数远超核数=线程池配置过大或线程泄漏（用完不回收），"
                          "常见于每请求起一个线程且没上限的老代码"]},
        ],
        "dones": [
            {"id": "done_not_high", "summary": "系统线程总数不高，pthread_create 失败多为单进程触碰了 "
                                               "ulimit -u（用户进程/线程上限）——查该用户的 nproc 软限制。"},
            {"id": "done_single_culprit", "summary": "某单进程线程数异常高，是线程泄漏或线程池无上限。"
                                                     "定位该进程后从应用侧限制线程池大小；紧急可重启该进程释放。"},
            {"id": "done_spread", "summary": "线程分散在多进程。核对是否某类框架/服务共性问题，"
                                             "或系统整体并发确实高需要上调 threads-max 与相关 ulimit。"},
        ],
    },
    {
        "id": "host.system.ulimit-exhausted", "name": "ulimit 文件句柄打满排查",
        "taxonomy": "host/system/ulimit-exhausted",
        "symptom": "Too many open files/句柄用满/accept 失败",
        "checks": [
            {"id": "sys_fd", "title": "查系统级 fd 使用与上限",
             "cmd": "echo \"used $(awk '{print $1}' /proc/sys/fs/file-nr) max $(cat /proc/sys/fs/file-max)\"",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.used > output.max * 0.8", "goto": "done_system_limit"},
                          {"when": "output.used <= output.max * 0.8", "goto": "proc_fd"}],
             "otherwise": "proc_fd",
             "cautions": ["file-nr 第一列是已分配 fd 数；系统级没满不代表进程级没满——"
                          "进程受 ulimit -n 单独约束"]},
            {"id": "proc_fd", "title": "找 fd 占用最多的进程",
             "cmd": "for p in /proc/[0-9]*; do echo \"$(ls $p/fd 2>/dev/null|wc -l) ${p##*/}\"; done | sort -rn | head -5",
             "parser": "generic/table-v1",
             "branches": [{"when": "rows[0].name > 5000", "goto": "done_proc_leak"},
                          {"when": "output.row_count > 0", "goto": "escalate"}],
             "otherwise": "escalate",
             "cautions": ["进程 fd 高但不涨=正常高并发；持续只涨不降=fd 泄漏（打开不关），"
                          "看是 socket 还是普通文件（ls -l /proc/PID/fd）"]},
        ],
        "dones": [
            {"id": "done_system_limit", "summary": "系统级 fd 接近 file-max。上调："
                                                   "sysctl -w fs.file-max=<更大值> 并写入 /etc/sysctl.conf 永久化。"},
            {"id": "done_proc_leak", "summary": "某进程 fd 数异常高，多为 fd 泄漏。临时缓解上调该服务的 "
                                                "LimitNOFILE（systemd）或 ulimit -n；根治要修应用（确保 close）。"},
        ],
    },
    {
        "id": "host.storage.inode-exhausted", "name": "inode 耗尽排查（空间够却报满）",
        "taxonomy": "host/storage/inode-exhausted",
        "symptom": "df 有空间但报 No space/inode 用满/建不了文件",
        "checks": [
            {"id": "check_inode", "title": "确认是否 inode 耗尽",
             "cmd": "df -i --output=ipcent / | tr -dc '0-9\\n' | tail -1",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value >= 95", "goto": "find_dirs"},
                          {"when": "output.value < 95", "goto": "done_not_inode"}],
             "otherwise": "find_dirs",
             "cautions": ["df 显示有空间却报 No space left，几乎总是 inode 耗尽——这是本 Skill 的存在意义"]},
            {"id": "find_dirs", "title": "定位海量小文件目录",
             "cmd": "for d in /var /tmp /home; do echo \"$(find $d -xdev 2>/dev/null | wc -l) $d\"; done | sort -rn | head",
             "parser": "generic/table-v1",
             "branches": [{"when": "rows[0].name > 100000", "goto": "done_found_dir"},
                          {"when": "output.row_count > 0", "goto": "escalate"}],
             "otherwise": "escalate",
             "cautions": ["典型元凶：session 文件、mail 队列、未清的临时文件、大量小日志。"
                          "处置走隔离/归档，别一把 rm -rf（可能误删业务），最终删除永远经过人"]},
        ],
        "dones": [
            {"id": "done_not_inode", "summary": "inode 未耗尽（<95%）。报 No space 若非容量满，"
                                                "可能是磁盘配额（quota）或 reserved blocks，转查这两项。"},
            {"id": "done_found_dir", "summary": "定位到海量小文件目录。确认业务不再需要后归档/清理该目录下的"
                                                "碎小文件；配 logrotate 或定期清理防复发。"},
        ],
    },
    {
        "id": "host.memory.slab-leak", "name": "内核 slab 内存泄漏排查",
        "taxonomy": "host/memory/slab-leak",
        "symptom": "内存被吃但没进程占用/slab 很大/available 低",
        "checks": [
            {"id": "check_slab", "title": "查 slab 占用总量",
             "cmd": "awk '/Slab:/{print \"slab_kb\", $2} /SReclaimable:/{print \"reclaim_kb\", $2}' /proc/meminfo",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.slab_kb > 4000000", "goto": "top_slab"},
                          {"when": "output.slab_kb <= 4000000", "goto": "done_slab_normal"}],
             "otherwise": "top_slab",
             "cautions": ["Slab 大但 SReclaimable 也大=多为 dentry/inode 缓存，可回收不算泄漏；"
                          "SUnreclaim 大才是真占用"]},
            {"id": "top_slab", "title": "看哪类 slab 对象最多",
             "cmd": "slabtop -o -s c 2>/dev/null | head -8",
             "parser": "generic/table-v1",
             "branches": [{"when": "output.row_count > 0", "goto": "done_found_slab"}],
             "otherwise": "escalate",
             "cautions": ["dentry/inode_cache 巨大常因海量文件遍历或未关闭 fd；网络类对象大看连接泄漏。"
                          "回收缓存：echo 2 > /proc/sys/vm/drop_caches（会短暂增加 IO，业务低峰做）"]},
        ],
        "dones": [
            {"id": "done_slab_normal", "summary": "slab 占用不高，available 低另有原因"
                                                  "（page cache 或匿名内存），转查 host/memory/cache-pressure。"},
            {"id": "done_found_slab", "summary": "定位到占用最大的 slab 对象类型。若是可回收缓存(dentry/inode)"
                                                 "可 drop_caches 缓解；若是不可回收对象持续增长，是内核/驱动泄漏，"
                                                 "记录对象类型升级排查。"},
        ],
    },
]
