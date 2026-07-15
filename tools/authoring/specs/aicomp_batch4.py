"""H-push aicomp 域批量 spec（第四批）——推理服务/显存泄漏/驱动持久化/多机拓扑。"""

_A = {"capability_level": "read", "connector": "ssh", "facts": ["os.family", "gpu.driver.version"]}

SPECS = [
    {**_A,
     "id": "aicomp.inference.gpu-underutilized", "name": "推理服务 GPU 利用率低排查",
     "taxonomy": "aicomp/inference/gpu-underutilized",
     "symptom": "推理 QPS 上不去/GPU 利用率低但延迟高/吞吐不达标/GPU 没吃满",
     "checks": [
        {"id": "check_util", "title": "查推理时 GPU 利用率",
         "cmd": "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | tr -dc '0-9\\n' | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value < 50", "goto": "check_batch"},
                      {"when": "output.value >= 50", "goto": "done_util_ok"}],
         "otherwise": "check_batch",
         "cautions": ["推理 GPU 利用率低+延迟高的典型原因是没做动态批处理(dynamic batching):请求一个个串行推,"
                      "GPU 大量空泡;吞吐瓶颈常在服务框架配置而非 GPU 本身"]},
        {"id": "check_batch", "title": "看是否单请求独占(未批处理)",
         "cmd": "nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null | sort -n | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_no_batching"},
                      {"when": "output.value == 0", "goto": "done_idle_service"}],
         "otherwise": "escalate",
         "cautions": ["提吞吐的杠杆:开动态批处理攒请求一起算、多实例/多 worker 填满 GPU、用 Triton/vLLM 这类"
                      "带批调度的推理框架;盲目加卡不如先把单卡吃满"]},
     ],
     "dones": [
        {"id": "done_util_ok", "summary": "GPU 利用率不低。吞吐不达标另查(前后处理/网络/序列化/客户端并发不足)。"},
        {"id": "done_no_batching", "summary": "GPU 有负载但利用率低,多为未批处理串行推理。开动态批处理(dynamic batching)、"
                                           "调大 max_batch_size 与队列延迟、部署多实例填满 GPU;换 Triton/vLLM 等带批调度框架。"},
        {"id": "done_idle_service", "summary": "GPU 上没有推理进程占用,服务可能没真正加载到 GPU 或请求没进来。"
                                            "确认模型加载到了 GPU(非 CPU 回退)、服务在监听、客户端确有请求打过来。"},
     ]},
    {**_A,
     "id": "aicomp.gpu.memory-leak", "name": "GPU 显存泄漏排查(占用只涨不降)",
     "taxonomy": "aicomp/gpu/memory-leak",
     "symptom": "GPU 显存只涨不降/长时间运行后 OOM/进程退出后显存没释放",
     "checks": [
        {"id": "check_orphan", "title": "查是否有已退出进程仍占显存",
         "cmd": "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1000", "goto": "check_procs"},
                      {"when": "output.value <= 1000", "goto": "done_mem_low"}],
         "otherwise": "check_procs",
         "cautions": ["显存'只涨不降'要分清:是运行中进程真的在累积(应用层泄漏,如没释放的中间张量/缓存),"
                      "还是崩溃进程没清干净残留占用——两者定位完全不同"]},
        {"id": "check_procs", "title": "看占显存的进程是否还活着",
         "cmd": "nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | while read p; do kill -0 $p 2>/dev/null || echo dead; done | grep -c dead",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_orphan_mem"},
                      {"when": "output.value == 0", "goto": "done_app_leak"}],
         "otherwise": "escalate",
         "cautions": ["nvidia-smi 有时显示已死进程仍占显存(驱动没回收);而进程都活着却显存涨=应用层泄漏。"
                      "MPS/容器环境残留更常见"]},
     ],
     "dones": [
        {"id": "done_mem_low", "summary": "显存占用不高。OOM 另查(峰值批次/碎片,见 aicomp.gpu.cuda-oom)。"},
        {"id": "done_orphan_mem", "summary": "有已退出进程残留占显存(崩溃没清干净)。确认无正常任务后清理残留进程/重置 GPU"
                                          "(nvidia-smi -r,需无活跃进程);容器/MPS 环境注意退出时的资源回收。"},
        {"id": "done_app_leak", "summary": "占显存进程都活着但显存持续涨=应用层泄漏。查代码是否累积张量/未清缓存"
                                        "(如 Python 引用没释放、循环里 append GPU 张量);用显存快照工具定位增长点。"},
     ]},
    {**_A,
     "id": "aicomp.gpu.persistence-mode-off", "name": "GPU 持久化模式未开排查",
     "taxonomy": "aicomp/gpu/persistence-mode-off",
     "symptom": "首次调用 GPU 慢/nvidia-smi 卡顿/驱动反复加载卸载/CUDA 初始化耗时长",
     "checks": [
        {"id": "check_pm", "title": "查持久化模式是否开启",
         "cmd": "nvidia-smi --query-gpu=persistence_mode --format=csv,noheader 2>/dev/null | grep -ic 'Disabled'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_daemon"},
                      {"when": "output.value == 0", "goto": "done_pm_on"}],
         "otherwise": "check_daemon",
         "cautions": ["持久化模式关闭时,没有进程用 GPU 内核就会卸载驱动状态,下次用又重新初始化——表现为首次"
                      "CUDA 调用/nvidia-smi 有明显延迟;训练/推理集群应常开持久化模式"]},
        {"id": "check_daemon", "title": "看是否运行 nvidia-persistenced 守护",
         "cmd": "systemctl is-active nvidia-persistenced 2>/dev/null | grep -ic '^active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_daemon_on"},
                      {"when": "output.value == 0", "goto": "done_enable_pm"}],
         "otherwise": "escalate",
         "cautions": ["老的 nvidia-smi -pm 1 方式已弃用,推荐用 nvidia-persistenced 守护进程维持持久化;"
                      "两者目的一致——让驱动常驻,避免反复初始化开销"]},
     ],
     "dones": [
        {"id": "done_pm_on", "summary": "持久化模式已开。首次慢另查(CUDA context 初始化、MIG、cgroup 限制、大模型加载)。"},
        {"id": "done_enable_pm", "summary": "持久化模式关且无守护进程。启用 nvidia-persistenced 并设开机自启,让驱动常驻;"
                                         "消除首次调用/nvidia-smi 的初始化延迟,适合常驻的训练推理节点。"},
        {"id": "done_daemon_on", "summary": "有守护进程但持久化仍显示关,核对 nvidia-persistenced 是否真生效/版本兼容、"
                                         "是否被其它配置覆盖;必要时重启该服务并复查 persistence_mode。"},
     ]},
    {**_A,
     "id": "aicomp.collective.nccl-topology-suboptimal", "name": "NCCL 拓扑选路不优排查",
     "taxonomy": "aicomp/collective/nccl-topology-suboptimal",
     "symptom": "多卡通信没走 NVLink/all-reduce 带宽低于预期/NCCL 走了 PCIe 或网络绕路",
     "checks": [
        {"id": "check_p2p", "title": "查卡间是否支持 P2P(NVLink/PCIe 直连)",
         "cmd": "nvidia-smi topo -m 2>/dev/null | grep -icE 'NV[0-9]+'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_env"},
                      {"when": "output.value == 0", "goto": "done_no_nvlink"}],
         "otherwise": "check_env",
         "cautions": ["nvidia-smi topo -m 的矩阵里 NV# 表示卡间走 NVLink,PIX/PXB 走 PCIe,SYS 跨 NUMA/QPI 最慢;"
                      "NCCL 会按拓扑选路,但选路不优时带宽远低于 NVLink 峰值——先看物理拓扑支持什么"]},
        {"id": "check_env", "title": "查是否有环境变量强制降级选路",
         "cmd": "env 2>/dev/null | grep -icE 'NCCL_P2P_DISABLE=1|NCCL_P2P_LEVEL=0|NCCL_SHM_DISABLE=1'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_p2p_disabled"},
                      {"when": "output.value == 0", "goto": "done_topo_ok"}],
         "otherwise": "escalate",
         "cautions": ["NCCL_P2P_DISABLE=1 之类环境变量(常为规避某些 bug 临时加的)会强制关掉 P2P,让通信绕远路;"
                      "'有 NVLink 却走得慢'先查是不是被这类变量降级了"]},
     ],
     "dones": [
        {"id": "done_no_nvlink", "summary": "卡间无 NVLink 直连(拓扑走 PCIe/SYS)。这是硬件拓扑决定的上限;"
                                         "多机/无 NVLink 机型要靠 IB/RoCE 与合理并行策略,别期望 NVLink 级带宽。"},
        {"id": "done_p2p_disabled", "summary": "有 NVLink 但被环境变量关了 P2P。核实 NCCL_P2P_DISABLE/P2P_LEVEL/SHM_DISABLE"
                                            "是否有必要(多为遗留的临时规避),去掉后让 NCCL 走 NVLink,带宽恢复。"},
        {"id": "done_topo_ok", "summary": "拓扑支持 NVLink 且无强制降级,选路应正常。带宽仍不达预期用 NCCL_DEBUG=INFO"
                                       "看实际选的 channel/协议、确认绑核与 NUMA 亲和、以及是否被其它进程抢占带宽。"},
     ]},
]
