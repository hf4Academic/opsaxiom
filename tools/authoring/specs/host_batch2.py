"""H-2 host 域批量 spec（第二批）。领域内容按运维知识填，生成器编译+求解+晋级。"""

SPECS = [
    {
        "id": "host.system.systemd-restart-loop", "name": "systemd 服务反复重启排查",
        "taxonomy": "host/system/systemd-restart-loop",
        "symptom": "服务一直重启/systemctl status 显示 activating/start-limit-hit",
        "checks": [
            {"id": "check_restarts", "title": "查该单元近期重启次数",
             "cmd": "systemctl show SERVICE -p NRestarts --value",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 5", "goto": "check_exit"},
                          {"when": "output.value <= 5", "goto": "done_stable"}],
             "otherwise": "check_exit",
             "cautions": ["Restart=always 时崩了会被拉起，掩盖真问题——NRestarts 高才暴露；"
                          "撞到 StartLimitBurst 会进 failed 且不再拉起（start-limit-hit）"]},
            {"id": "check_exit", "title": "查最后一次退出原因",
             "cmd": "systemctl show SERVICE -p ExecMainStatus -p Result | grep -c 'Result=exit-code\\|ExecMainStatus=[1-9]'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_app_crash"},
                          {"when": "output.value == 0", "goto": "done_oom_or_signal"}],
             "otherwise": "escalate",
             "cautions": ["Result=oom-kill 说明被 OOM 杀（关联 memory/oom-kill）；"
                          "signal 类退出看 journalctl -u 的堆栈，别只盯 systemd 状态"]},
        ],
        "dones": [
            {"id": "done_stable", "summary": "重启次数不高，服务基本稳定。若仍偶发，观察是否周期性"
                                             "（如内存缓慢泄漏后被杀），配合 journal 看时间规律。"},
            {"id": "done_app_crash", "summary": "以非零码退出=应用自身崩溃。看 journalctl -u SERVICE 的最后"
                                                "几十行定位崩溃点；临时用 RestartSec 拉长重启间隔避免 CPU 打满，根治靠修应用。"},
            {"id": "done_oom_or_signal", "summary": "非退出码型异常（信号/OOM）。查是否 Result=oom-kill；"
                                                    "是则该服务内存超限，调 MemoryMax 或修泄漏；否则看信号来源。"},
        ],
    },
    {
        "id": "host.network-stack.arp-table-full", "name": "本机 ARP/邻居表满排查",
        "taxonomy": "host/network-stack/arp-table-full",
        "symptom": "neighbour table overflow/dmesg 报 arp 表满/新连接偶发不通",
        "checks": [
            {"id": "count_neigh", "title": "统计邻居表项数与 gc 阈值",
             "cmd": "echo \"entries $(ip neigh | wc -l) thresh3 $(cat /proc/sys/net/ipv4/neigh/default/gc_thresh3)\"",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.entries > output.thresh3 * 0.8", "goto": "check_stale"},
                          {"when": "output.entries <= output.thresh3 * 0.8", "goto": "done_not_full"}],
             "otherwise": "check_stale",
             "cautions": ["gc_thresh3 是硬上限，超了内核直接丢新邻居并 dmesg 报 overflow；"
                          "大二层/大量 VIP 环境容易撞"]},
            {"id": "check_stale", "title": "看是否大量 FAILED/STALE 表项",
             "cmd": "ip neigh | grep -c 'FAILED\\|INCOMPLETE'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 100", "goto": "done_scan_or_fail"},
                          {"when": "output.value <= 100", "goto": "done_legit_scale"}],
             "otherwise": "escalate",
             "cautions": ["大量 FAILED 常因扫描/探测把不存在的 IP 塞进表；真实规模大则是网段设计问题"]},
        ],
        "dones": [
            {"id": "done_not_full", "summary": "邻居表未接近上限，偶发不通另有原因，转查 conntrack 或丢包。"},
            {"id": "done_scan_or_fail", "summary": "大量 FAILED/INCOMPLETE 表项挤占空间。排查谁在扫描不存在的"
                                                   " IP；临时上调 gc_thresh1/2/3（sysctl net.ipv4.neigh.default.gc_thresh*）。"},
            {"id": "done_legit_scale", "summary": "表项多为有效邻居=网段内主机确实多。上调 gc_thresh3 并写入"
                                                  " sysctl.conf；长期考虑拆网段缩小广播/邻居域。"},
        ],
    },
    {
        "id": "host.storage.mount-failed", "name": "挂载失败/开机卡挂载排查",
        "taxonomy": "host/storage/mount-failed",
        "symptom": "mount 失败/开机卡在挂载/emergency mode/fstab 报错",
        "checks": [
            {"id": "check_failed", "title": "查有无失败的 mount 单元",
             "cmd": "systemctl --failed --type=mount 2>/dev/null | grep -c '\\.mount'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "check_device"},
                          {"when": "output.value == 0", "goto": "done_no_fail"}],
             "otherwise": "check_device",
             "cautions": ["fstab 里挂载项写错会让开机卡进 emergency mode——加 nofail 选项可让非关键盘"
                          "挂不上也不阻塞开机"]},
            {"id": "check_device", "title": "确认设备/UUID 是否存在",
             "cmd": "for u in $(awk '!/^#/ && /UUID/{print $1}' /etc/fstab); do blkid | grep -c \"$u\"; done | grep -c '^0'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_device_gone"},
                          {"when": "output.value == 0", "goto": "done_fs_or_opts"}],
             "otherwise": "escalate",
             "cautions": ["设备名 /dev/sdb 会因插拔顺序变，fstab 用 UUID 才稳；UUID 找不到=盘掉了或换了"]},
        ],
        "dones": [
            {"id": "done_no_fail", "summary": "没有失败的挂载单元。若手动 mount 报错，看具体错误"
                                              "（文件系统类型不对/选项非法/目标目录不存在）。"},
            {"id": "done_device_gone", "summary": "fstab 里某 UUID 对应设备不存在——盘掉了、换了或没插好。"
                                                  "确认硬件后更新 fstab；非关键盘加 nofail 防止阻塞开机。"},
            {"id": "done_fs_or_opts", "summary": "设备在但挂不上，多为文件系统损坏（需 fsck）或挂载选项非法。"
                                                 "先 fsck 检查，再核对 fstab 的类型与 options。"},
        ],
    },
    {
        "id": "host.cpu.iowait-high", "name": "CPU iowait 高排查",
        "taxonomy": "host/cpu/iowait-high",
        "symptom": "iowait 高/CPU 大量时间等 IO/系统响应慢",
        "checks": [
            {"id": "check_iowait", "title": "确认 iowait 占比",
             "cmd": "top -bn1 | awk '/Cpu\\(s\\)/{for(i=1;i<=NF;i++) if($i ~ /wa/) print \"wa\", $(i-1)}'",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.wa > 20", "goto": "find_io"},
                          {"when": "output.wa <= 20", "goto": "done_not_io"}],
             "otherwise": "find_io",
             "cautions": ["iowait 高只说明 CPU 在等 IO，不等于 IO 一定是瓶颈（也可能核少放大了占比）；"
                          "要结合实际 IOPS/await 判断"]},
            {"id": "find_io", "title": "找占 IO 最多的进程",
             "cmd": "iotop -bon1 2>/dev/null | head -8 || pidstat -d 1 1 | sort -k5 -rn | head",
             "parser": "generic/table-v1",
             "branches": [{"when": "output.row_count > 0", "goto": "done_found_io"}],
             "otherwise": "escalate",
             "cautions": ["iotop 需 root 和 CONFIG_TASK_IO_ACCOUNTING；没有则用 pidstat -d。"
                          "常见元凶：日志狂写、大文件拷贝、数据库 checkpoint、内存不足导致 swap IO"]},
        ],
        "dones": [
            {"id": "done_not_io", "summary": "iowait 不高，慢的原因不在 IO 等待。转查 CPU 负载、"
                                             "单核饱和或应用自身。"},
            {"id": "done_found_io", "summary": "定位到 IO 大户。区分：是正常业务 IO（考虑限速/错峰/换更快盘）"
                                               "还是异常（日志狂写/swap 抖动——后者先解决内存问题）。"},
        ],
    },
    {
        "id": "host.system.dmesg-hardware-error", "name": "内核硬件报错排查（MCE/EDAC）",
        "taxonomy": "host/system/dmesg-hardware-error",
        "symptom": "dmesg 有 Hardware Error/MCE/EDAC 报错/怀疑硬件问题",
        "checks": [
            {"id": "scan_dmesg", "title": "扫描内核硬件错误关键字",
             "cmd": "dmesg -l err,crit 2>/dev/null | grep -icE 'Hardware Error|Machine check|EDAC|mce'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "classify"},
                          {"when": "output.value == 0", "goto": "done_no_hw_err"}],
             "otherwise": "classify",
             "cautions": ["dmesg 时间戳是相对开机的，配合 -T 转成人类时间判断是不是近期发生"]},
            {"id": "classify", "title": "区分内存还是 CPU/PCIe 错误",
             "cmd": "dmesg 2>/dev/null | grep -iE 'memory|DIMM|EDAC' | grep -icE 'corrected|CE'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_mem_ce"},
                          {"when": "output.value == 0", "goto": "done_other_hw"}],
             "otherwise": "escalate",
             "cautions": ["CE(Corrected Error)是已纠正的可容忍错误，但持续增长预示 DIMM 将坏；"
                          "UE(Uncorrected)是致命错误必须立即换件。别把 CE 当 UE 慌，也别忽视 CE 的趋势"]},
        ],
        "dones": [
            {"id": "done_no_hw_err", "summary": "内核日志无硬件错误。问题不在硬件层，转查软件/驱动。"},
            {"id": "done_mem_ce", "summary": "有内存可纠正错误(CE)。单发无害，但同一 DIMM 持续 CE 预示劣化——"
                                             "用 edac-util/mcelog 定位到具体 DIMM，纳入巡检，频繁则计划性更换。"},
            {"id": "done_other_hw", "summary": "非内存类硬件错误（CPU/PCIe/总线）。收集完整 dmesg 与 mcelog，"
                                               "对照厂商工具（如 IPMI SEL）定位部件，多数需报修。"},
        ],
    },
    {
        "id": "host.network-stack.tcp-retrans-high", "name": "TCP 重传率高排查",
        "taxonomy": "host/network-stack/tcp-retrans-high",
        "symptom": "TCP 重传多/网络时快时慢/吞吐上不去",
        "checks": [
            {"id": "check_retrans", "title": "查 TCP 重传段计数",
             "cmd": "nstat -az 2>/dev/null | awk '/TcpRetransSegs/{print \"retrans\", $2} /TcpOutSegs/{print \"out\", $2}'",
             "parser": "generic/kv-num-v1",
             "branches": [{"when": "output.retrans > 10000", "goto": "check_where"},
                          {"when": "output.retrans <= 10000", "goto": "done_low"}],
             "otherwise": "check_where",
             "cautions": ["nstat 计数是自开机累计，第一次看基数大是正常的——关键看增长速率，"
                          "或用 nstat 两次间隔取差"]},
            {"id": "check_where", "title": "看是本机发送侧还是接收侧丢",
             "cmd": "ss -ti 2>/dev/null | grep -c 'retrans:'",
             "parser": "generic/count-v1",
             "branches": [{"when": "output.value > 0", "goto": "done_active_retrans"},
                          {"when": "output.value == 0", "goto": "done_check_peer"}],
             "otherwise": "escalate",
             "cautions": ["ss -ti 能看到每连接的 retrans/rtt；重传集中在少数连接=特定路径问题，"
                          "普遍重传=链路/网卡/中间设备丢包"]},
        ],
        "dones": [
            {"id": "done_low", "summary": "重传计数不高，吞吐问题另有原因（窗口/RTT/应用），"
                                          "看 ss -ti 的 cwnd 与 rtt。"},
            {"id": "done_active_retrans", "summary": "本机有活跃重传连接。定位到具体对端/路径后逐跳查丢包；"
                                                     "网卡侧看 ethtool -S 的 drop/error 计数，排除 ring buffer 满。"},
            {"id": "done_check_peer", "summary": "本机侧未见活跃重传，可能是接收侧或对端问题。"
                                                 "在对端同样查重传，或抓包看是谁在重传。"},
        ],
    },
]
