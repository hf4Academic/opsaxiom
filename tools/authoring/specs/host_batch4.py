"""H-push host 域批量 spec（第四批）——中断/NUMA/磁盘IO错误/端口耗尽/熵池/cgroup限流。"""

_H = {"capability_level": "read", "connector": "ssh", "facts": ["os.family"]}

SPECS = [
    {**_H,
     "id": "host.cpu.irq-storm", "name": "中断风暴排查(软/硬中断打高 CPU)",
     "taxonomy": "host/cpu/irq-storm",
     "symptom": "CPU si/hi 很高/软中断吃满一个核/网卡收包丢包但带宽不高/系统卡",
     "checks": [
        {"id": "check_softirq", "title": "查软中断 CPU 占比",
         "cmd": "top -bn1 2>/dev/null | awk '/%Cpu/{gsub(/[^0-9. ]/,\"\"); print \"si\", $NF}' | head -1",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.si > 20", "goto": "check_irqbalance"},
                      {"when": "output.si <= 20", "goto": "done_si_ok"}],
         "otherwise": "check_irqbalance",
         "cautions": ["软中断(si)高常因网卡收发大量小包、单队列没做 RSS 多队列、或中断全落在一个核;"
                      "现象常是'一个 CPU 核 100% 全在 si,其余核闲'——看是否中断没打散"]},
        {"id": "check_irqbalance", "title": "看中断是否集中在单核(未均衡)",
         "cmd": "systemctl is-active irqbalance 2>/dev/null | grep -ic '^active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_no_irqbalance"},
                      {"when": "output.value > 0", "goto": "done_irq_tune"}],
         "otherwise": "escalate",
         "cautions": ["irqbalance 没跑,中断容易全压在 CPU0;但高性能网卡场景反而要手动绑核(关 irqbalance+"
                      "手工 affinity)——先看当前是哪种,别盲目开关"]},
     ],
     "dones": [
        {"id": "done_si_ok", "summary": "软中断占比不高。CPU 卡另查(us/sy 高/负载/steal/具体进程)。"},
        {"id": "done_no_irqbalance", "summary": "irqbalance 未运行,中断可能集中单核。启用 irqbalance 打散中断,"
                                             "或针对网卡开 RSS 多队列并手工绑核;缓解单核 si 打满导致的丢包/卡顿。"},
        {"id": "done_irq_tune", "summary": "irqbalance 在跑但 si 仍高,多为收包量大或单队列瓶颈。给网卡开多队列(RSS/RPS)、"
                                        "调大 ring buffer、开 GRO;高吞吐场景考虑手工中断绑核到多个 CPU。"},
     ]},
    {**_H,
     "id": "host.memory.numa-imbalance", "name": "NUMA 内存不均衡排查",
     "taxonomy": "host/memory/numa-imbalance",
     "symptom": "内存访问慢/一个 NUMA 节点内存满另一个空/跨节点访问多/性能抖动",
     "checks": [
        {"id": "check_foreign", "title": "查跨 NUMA 节点访问计数",
         "cmd": "numastat 2>/dev/null | awk '/numa_foreign/{s=0; for(i=2;i<=NF;i++)s+=$i; print \"foreign\", s}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.foreign > 1000000", "goto": "check_free"},
                      {"when": "output.foreign <= 1000000", "goto": "done_numa_ok"}],
         "otherwise": "check_free",
         "cautions": ["numa_foreign 高=进程在别的节点分了内存(本地节点不够),跨节点访问延迟高一截;"
                      "大内存进程(DB/JVM)没做 NUMA 亲和时最容易踩"]},
        {"id": "check_free", "title": "看各节点空闲内存是否悬殊",
         "cmd": "numactl -H 2>/dev/null | grep -c 'node [0-9]* free'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1", "goto": "done_imbalanced"},
                      {"when": "output.value <= 1", "goto": "done_single_node"}],
         "otherwise": "escalate",
         "cautions": ["单节点内存被某进程吃满、另一节点空闲,会触发跨节点分配甚至该节点内的回收抖动;"
                      "绑 NUMA(numactl --membind/--cpunodebind)或交给自动均衡要按业务权衡"]},
     ],
     "dones": [
        {"id": "done_numa_ok", "summary": "跨节点访问不高。内存慢另查(带宽/大页/交换/具体进程访存模式)。"},
        {"id": "done_imbalanced", "summary": "NUMA 节点间不均衡致跨节点访问。给大内存进程做 NUMA 亲和"
                                          "(numactl 绑 CPU+内存到同节点)、或按节点均分负载;数据库/JVM 尤其受益于亲和绑定。"},
        {"id": "done_single_node", "summary": "疑似单节点或数据不足。确认机器是否真多 NUMA 节点;若是,核对进程内存策略"
                                           "(interleave vs bind),避免关键进程内存溢到远端节点。"},
     ]},
    {**_H,
     "id": "host.storage.disk-io-error", "name": "磁盘 I/O 错误排查(坏道/介质错误)",
     "taxonomy": "host/storage/disk-io-error",
     "symptom": "dmesg 报 I/O error/文件读写报错/磁盘坏道/介质错误/EXT4-fs error",
     "checks": [
        {"id": "check_dmesg", "title": "查内核 I/O 错误日志",
         "cmd": "dmesg 2>/dev/null | grep -icE 'I/O error|Medium Error|critical medium|blk_update_request|EXT4-fs error|XFS.*error'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_ro"},
                      {"when": "output.value == 0", "goto": "done_no_ioerr"}],
         "otherwise": "check_ro",
         "cautions": ["内核 I/O error/Medium Error 是硬盘物理层报上来的,基本坐实介质/坏道问题——"
                      "别只重试,继续读写坏道可能扩大损坏,且文件系统可能已受损"]},
        {"id": "check_ro", "title": "看文件系统是否已被踢成只读",
         "cmd": "mount 2>/dev/null | grep -c 'ro,\\|(ro)\\| ro '",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_fs_readonly"},
                      {"when": "output.value == 0", "goto": "done_io_error"}],
         "otherwise": "escalate",
         "cautions": ["文件系统检测到错误会自我保护重挂为只读(errors=remount-ro),此时业务写全失败;"
                      "重挂读写前必须先 fsck 修复,盲目 remount rw 可能加剧损坏"]},
     ],
     "dones": [
        {"id": "done_no_ioerr", "summary": "无内核 I/O 错误。读写报错另查(权限/空间/inode/挂载/上层应用)。"},
        {"id": "done_fs_readonly", "summary": "文件系统因 I/O 错误被踢成只读(自我保护)。先备份可读数据,卸载后 fsck 修复;"
                                           "结合 SMART 判断磁盘是否需更换,坏盘不要继续投产。"},
        {"id": "done_io_error", "summary": "有 I/O 错误但 FS 尚可写。尽快备份数据、查 SMART 确认磁盘健康"
                                        "(见 host.storage.smart-failing)、规划换盘;坏道会扩散,别拖到 FS 崩。"},
     ]},
    {**_H,
     "id": "host.network-stack.ephemeral-port-exhausted", "name": "临时端口耗尽排查(连不出去)",
     "taxonomy": "host/network-stack/ephemeral-port-exhausted",
     "symptom": "对外发起连接失败/cannot assign requested address/EADDRNOTAVAIL/端口用尽",
     "checks": [
        {"id": "check_count", "title": "查出方向连接占用的端口数",
         "cmd": "ss -tanH state established state time-wait 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 25000", "goto": "check_timewait"},
                      {"when": "output.value <= 25000", "goto": "done_ports_ok"}],
         "otherwise": "check_timewait",
         "cautions": ["主动发起连接用的是临时端口(ip_local_port_range,默认约 2.8 万个);高并发短连接把它们"
                      "占满(尤其大量 TIME_WAIT)就会 EADDRNOTAVAIL——连不出去不代表对端有问题"]},
        {"id": "check_timewait", "title": "看是否大量 TIME_WAIT 占着端口",
         "cmd": "ss -tanH state time-wait 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 10000", "goto": "done_timewait_heavy"},
                      {"when": "output.value <= 10000", "goto": "done_range_small"}],
         "otherwise": "escalate",
         "cautions": ["TIME_WAIT 是主动关闭方留的 2MSL 状态,短连接风暴下堆积很快;可开 tw_reuse(客户端侧)、"
                      "扩大 port_range、或改用长连接/连接池从根上减少端口消耗"]},
     ],
     "dones": [
        {"id": "done_ports_ok", "summary": "临时端口占用不高。连不出去另查(目标端口/防火墙/路由/DNS/对端拒绝)。"},
        {"id": "done_timewait_heavy", "summary": "大量 TIME_WAIT 占满临时端口。客户端开 net.ipv4.tcp_tw_reuse、"
                                              "扩大 ip_local_port_range;根治是改长连接/连接池,减少短连接创建销毁频率。"},
        {"id": "done_range_small", "summary": "端口紧张但 TIME_WAIT 不多,可能是并发连接确实多或 port_range 太窄。"
                                           "扩大 ip_local_port_range、复用连接;确认没有连接泄漏(建了不关)。"},
     ]},
    {**_H,
     "id": "host.system.entropy-low", "name": "熵池不足排查(加密/启动卡)",
     "taxonomy": "host/system/entropy-low",
     "symptom": "服务启动卡在生成密钥/TLS 握手慢/getrandom 阻塞/熵池耗尽",
     "checks": [
        {"id": "check_entropy", "title": "查可用熵值",
         "cmd": "cat /proc/sys/kernel/random/entropy_avail 2>/dev/null | awk '{print \"entropy\", $1}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.entropy < 256", "goto": "check_rng"},
                      {"when": "output.entropy >= 256", "goto": "done_entropy_ok"}],
         "otherwise": "check_rng",
         "cautions": ["熵池过低时,阻塞式随机源(老内核 /dev/random、getrandom 早期启动)会等到攒够熵才返回,"
                      "表现为'启动/握手莫名卡几十秒';虚拟机/无硬件熵源的环境尤其常见"]},
        {"id": "check_rng", "title": "看是否有熵补充服务",
         "cmd": "systemctl is-active rng-tools rngd haveged 2>/dev/null | grep -ic '^active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_rng_running"},
                      {"when": "output.value == 0", "goto": "done_no_rng"}],
         "otherwise": "escalate",
         "cautions": ["现代内核(5.x+)的 CRNG 一旦初始化就不再阻塞,熵低多不再是问题;但老内核/特殊场景仍需"
                      "haveged 或硬件 RNG(rng-tools 接 /dev/hwrng)补熵"]},
     ],
     "dones": [
        {"id": "done_entropy_ok", "summary": "可用熵充足。启动/握手卡另查(DNS 反解超时、依赖服务、磁盘 IO)。"},
        {"id": "done_no_rng", "summary": "熵低且无补熵服务。装并启用 haveged 或 rng-tools(有硬件 RNG 时接 /dev/hwrng);"
                                      "虚拟机可用 virtio-rng 透传宿主熵源,消除加密操作的阻塞。"},
        {"id": "done_rng_running", "summary": "已有补熵服务但熵仍低,确认它是否真在补(haveged 质量/rngd 数据源)、"
                                           "内核版本是否老到会阻塞;新内核基本无需担心,老环境则加强熵源。"},
     ]},
    {**_H,
     "id": "host.cpu.cgroup-throttle", "name": "cgroup CPU 限流排查(容器算力上不去)",
     "taxonomy": "host/cpu/cgroup-throttle",
     "symptom": "容器 CPU 用不满上限就被限/进程周期性卡顿/nr_throttled 增长/延迟毛刺",
     "checks": [
        {"id": "check_throttled", "title": "查 cgroup CFS 被限流次数",
         "cmd": "cat /sys/fs/cgroup/cpu.stat 2>/dev/null | awk '/nr_throttled/{print \"throttled\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.throttled > 0", "goto": "check_periods"},
                      {"when": "output.throttled <= 0", "goto": "done_no_throttle"}],
         "otherwise": "check_periods",
         "cautions": ["nr_throttled 增长=进程在 CFS 周期内用完配额被强制暂停到下周期,表现为周期性卡顿/毛刺,"
                      "哪怕整机 CPU 还很闲——这是'限额'不是'没资源',别去查整机负载"]},
        {"id": "check_periods", "title": "看被限流的时间占比是否高",
         "cmd": "cat /sys/fs/cgroup/cpu.stat 2>/dev/null | awk '/throttled_usec|throttled_time/{print \"tusec\", $2}' | head -1",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.tusec > 1000000", "goto": "done_heavy_throttle"},
                      {"when": "output.tusec <= 1000000", "goto": "done_light_throttle"}],
         "otherwise": "escalate",
         "cautions": ["限流时间占比高说明 limit 设得对业务太紧;调大 cpu.max/limits.cpu 或放宽配额,"
                      "多线程应用还要注意配额和线程数匹配(配额小但线程多,极易频繁触顶)"]},
     ],
     "dones": [
        {"id": "done_no_throttle", "summary": "无 CFS 限流。容器慢另查(整机负载/内存/IO/应用自身/其它 cgroup 控制器)。"},
        {"id": "done_heavy_throttle", "summary": "严重 CPU 限流,配额对业务太紧。调大容器 CPU limit/cpu.max,"
                                              "或减少并发线程数与配额匹配;整机有余量时适度放宽,消除周期性毛刺。"},
        {"id": "done_light_throttle", "summary": "轻度限流,偶发触顶。观察是否业务峰值短暂超配额;若毛刺可接受可不动,"
                                              "否则小幅上调配额留出余量,避免峰值被 CFS 掐。"},
     ]},
]
