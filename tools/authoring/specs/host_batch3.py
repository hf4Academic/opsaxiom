"""H-2 host 域批量 spec（第三批，收尾）。"""

SPECS = [
    {
        "id": "host.memory.hugepage-misconfig", "name": "大页配置不当排查",
        "taxonomy": "host/memory/hugepage-misconfig",
        "symptom": "应用申请大页失败/HugePages 配了没生效/数据库启动报大页不足",
        "checks": [
            {"id": "check_huge", "title": "查大页总数与空闲",
             "cmd": "awk '/HugePages_Total/{print \"total\",$2} /HugePages_Free/{print \"free\",$2}' /proc/meminfo",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.total == 0", "goto": "done_not_allocated"},
                          {"when": "output.total > 0", "goto": "check_thp"}],
             "otherwise": "check_thp",
             "cautions": ["HugePages_Total=0 说明没预留大页；预留要在内存碎片化前做（开机早期或 boot 参数），"
                          "运行期临时预留常因碎片化拿不满"]},
            {"id": "check_thp", "title": "看透明大页(THP)是否干扰",
             "cmd": "cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null | grep -c '\\[always\\]'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_thp_on"},
                          {"when": "output.value == 0", "goto": "done_alloc_ok"}],
             "otherwise": "escalate",
             "cautions": ["THP=always 对 Redis/Mongo/Oracle 常带来延迟尖刺（内存规整卡顿），"
                          "这些数据库官方建议关 THP——别和显式 HugePages 混为一谈"]},
        ],
        "dones": [
            {"id": "done_not_allocated", "summary": "未预留大页(Total=0)。在 sysctl 配 vm.nr_hugepages 或"
                                                    " GRUB 加 hugepages= 参数并重启，确保碎片化前预留足量。"},
            {"id": "done_thp_on", "summary": "THP=always。对延迟敏感数据库建议改为 madvise 或 never"
                                             "（echo never > .../enabled 并写进开机脚本），消除内存规整引起的尖刺。"},
            {"id": "done_alloc_ok", "summary": "大页已预留且 THP 未开 always。若应用仍申请失败，核对其"
                                               "请求的大页数量/尺寸(2M vs 1G)与实际预留是否匹配。"},
        ],
    },
    {
        "id": "host.process.unexpected-exit", "name": "进程莫名退出排查",
        "taxonomy": "host/process/unexpected-exit",
        "symptom": "服务自己挂了没日志/进程莫名消失/没留下堆栈",
        "checks": [
            {"id": "check_oom", "title": "先排除被 OOM 杀",
             "cmd": "dmesg -T 2>/dev/null | grep -icE 'Killed process|oom-kill|Out of memory'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_oom"},
                          {"when": "output.value == 0", "goto": "check_journal"}],
             "otherwise": "check_journal",
             "cautions": ["'没日志的消失'第一嫌疑永远是 OOM——被内核 SIGKILL 的进程来不及写任何日志"]},
            {"id": "check_journal", "title": "查有无 core dump 或信号记录",
             "cmd": "coredumpctl list --no-pager 2>/dev/null | grep -c SERVICE || journalctl --since '-1h' 2>/dev/null | grep -icE 'segfault|core dumped'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_crash"},
                          {"when": "output.value == 0", "goto": "done_no_trace"}],
             "otherwise": "escalate",
             "cautions": ["段错误会留 core（若开了 core dump）；没开 core 时 segfault 也会进 dmesg。"
                          "生产建议开 coredumpctl 便于事后分析"]},
        ],
        "dones": [
            {"id": "done_oom", "summary": "被 OOM Killer 杀掉——这就是'没日志消失'的原因。查该进程内存增长"
                                          "（泄漏或配置过大），限制 MemoryMax 或修泄漏；转 memory/oom-kill 细查。"},
            {"id": "done_crash", "summary": "有崩溃痕迹(core/segfault)。用 coredumpctl gdb 分析 core 定位崩溃点，"
                                            "或看 segfault 的地址与库定位问题模块。"},
            {"id": "done_no_trace", "summary": "既非 OOM 也无崩溃痕迹。可能是被外部信号杀（人/脚本/编排器）"
                                               "或正常退出被误判——查是否有 supervisor/k8s 主动杀，开审计看 kill 来源。"},
        ],
    },
    {
        "id": "host.storage.iops-latency-mismatch", "name": "磁盘延迟高但利用率不高排查",
        "taxonomy": "host/storage/iops-latency-mismatch",
        "symptom": "磁盘响应慢/await 高但 util 不满/IO 不多却慢",
        "checks": [
            {"id": "check_await", "title": "查 await 与 util",
             "cmd": "iostat -dx 1 2 2>/dev/null | awk '/^[sv]d|nvme/{a=$(NF-1); u=$NF} END{print \"await\", a; print \"util\", u}'",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.await > 20", "goto": "check_pattern"},
                          {"when": "output.await <= 20", "goto": "done_await_ok"}],
             "otherwise": "check_pattern",
             "cautions": ["await 高 util 低=单次 IO 慢但队列不满，多为单次大 IO、fsync 频繁或后端存储"
                          "（云盘/网络存储）本身延迟高，不是本地盘打满"]},
            {"id": "check_pattern", "title": "看 IO 是否以同步写/小 IO 为主",
             "cmd": "iostat -dx 1 2 2>/dev/null | awk '/^[sv]d|nvme/{print \"wps\", $(2)}' | tail -1",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.wps > 0", "goto": "done_sync_write"},
                          {"when": "output.wps <= 0", "goto": "done_backend_latency"}],
             "otherwise": "escalate",
             "cautions": ["频繁 fsync(数据库/日志)会让每次写都等落盘，await 天然高；这不是故障是特性，"
                          "优化方向是 IO 合并/换更快介质，而非'修盘'"]},
        ],
        "dones": [
            {"id": "done_await_ok", "summary": "await 不高，慢的原因不在磁盘延迟。转查是否 CPU/内存"
                                              "或应用自身。"},
            {"id": "done_sync_write", "summary": "以同步写为主，await 高是 fsync 等落盘的固有代价。优化："
                                                 "应用侧批量提交/组提交、开写缓存(权衡掉电风险)、换 NVMe/更快存储。"},
            {"id": "done_backend_latency", "summary": "await 高但非本地同步写主导，多为后端存储(云盘/SAN/NFS)"
                                                      "本身延迟。核对存储侧指标与 QoS 限速，非本机能修则联系存储团队。"},
        ],
    },
    {
        "id": "host.provision.baseline-drift", "name": "主机基线配置漂移排查",
        "taxonomy": "host/provision/baseline-drift",
        "symptom": "机器配置和基线不一致/谁改了 sysctl/参数被人动过",
        "checks": [
            {"id": "check_sysctl", "title": "抽查关键内核参数是否偏离基线",
             "cmd": "sysctl -n net.ipv4.ip_forward net.ipv4.conf.all.rp_filter vm.swappiness 2>/dev/null | paste -sd' ' | awk '{print \"forward\",$1; print \"rpfilter\",$2; print \"swappiness\",$3}'",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.swappiness > 30", "goto": "done_drift_found"},
                          {"when": "output.swappiness <= 30", "goto": "check_selinux"}],
             "otherwise": "check_selinux",
             "cautions": ["基线值因业务而异（此处 swappiness 阈值仅示例）——真实基线应来自你的标准，"
                          "本 Skill 演示漂移检测方法而非规定具体值"]},
            {"id": "check_selinux", "title": "查安全模块状态是否被关",
             "cmd": "getenforce 2>/dev/null | grep -ic 'disabled\\|permissive'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_security_off"},
                          {"when": "output.value == 0", "goto": "done_baseline_ok"}],
             "otherwise": "escalate",
             "cautions": ["SELinux 被临时 setenforce 0 不会持久但会留隐患；被改 config 则重启后仍关——"
                          "两者危害不同，要区分临时态与配置态"]},
        ],
        "dones": [
            {"id": "done_drift_found", "summary": "检测到内核参数偏离基线。对照标准基线恢复"
                                                  "（sysctl -w 临时、写 sysctl.conf 持久）；查审计日志追谁改的、为什么。"},
            {"id": "done_security_off", "summary": "安全模块被关(disabled/permissive)。确认是否有意为之；"
                                                   "无正当理由则恢复 enforcing，并排查是谁在什么时候关的。"},
            {"id": "done_baseline_ok", "summary": "抽查项符合基线。全量核查建议用配置管理工具(ansible/salt)"
                                                  "跑一次 diff，本 Skill 只做快速抽检。"},
        ],
    },
]
