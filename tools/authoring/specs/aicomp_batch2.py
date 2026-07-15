"""H-6 aicomp 域批量 spec（第二批）——NCCL/训练/scheduling。"""

_A = {"capability_level": "read", "connector": "ssh", "facts": ["os.family"]}

SPECS = [
    {**_A,
     "id": "aicomp.collective.nccl-timeout", "name": "NCCL 通信超时/训练卡死排查",
     "taxonomy": "aicomp/collective/nccl-timeout",
     "symptom": "训练卡在某步不动/NCCL watchdog timeout/all-reduce 超时",
     "checks": [
        {"id": "check_log", "title": "查训练日志的 NCCL 超时",
         "cmd": "tail -300 /var/log/training.log 2>/dev/null | grep -icE 'NCCL.*timeout|Watchdog|collective.*timed out'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_gpu"},
                      {"when": "output.value == 0", "goto": "done_no_timeout"}],
         "otherwise": "check_gpu",
         "cautions": ["NCCL watchdog timeout 常是'某个 rank 卡住导致 all-reduce 集合等不齐'——"
                      "掉的那个 rank 才是根因，超时报错的 rank 只是受害者"]},
        {"id": "check_gpu", "title": "查是否有 GPU 掉卡/无进程",
         "cmd": "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | tr -dc '0-9\\n' | sort -n | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_rank_stuck"},
                      {"when": "output.value > 0", "goto": "done_network_stall"}],
         "otherwise": "escalate",
         "cautions": ["有卡利用率 0 而别的卡在跑=该 rank 已卡死(等它的集合永远等不到)；"
                      "所有卡都 0=可能整体死锁或已崩"]},
     ],
     "dones": [
        {"id": "done_no_timeout", "summary": "无 NCCL 超时。训练卡另查(数据加载/checkpoint/死锁)。"},
        {"id": "done_rank_stuck", "summary": "有 rank 卡死(利用率 0)拖垮集合通信。定位卡住的 rank/节点，"
                                           "查其 GPU 是否掉卡(XID)、进程是否 D 状态、是否 OOM；该 rank 恢复后集合才能完成。"},
        {"id": "done_network_stall", "summary": "GPU 都在跑但集合通信超时，多为网络/NVLink 问题导致某段通信卡住。"
                                               "查 NVLink/IB 链路、NCCL 环境变量(NCCL_DEBUG=INFO 看卡在哪个 channel)。"},
     ]},
    {**_A,
     "id": "aicomp.training.checkpoint-slow", "name": "Checkpoint 保存慢/训练周期性卡顿排查",
     "taxonomy": "aicomp/training/checkpoint-slow",
     "symptom": "保存 checkpoint 很慢/训练每隔一段卡一下/存盘阶段 GPU 空转",
     "checks": [
        {"id": "check_io", "title": "查 checkpoint 目录所在盘的写入能力",
         "cmd": "iostat -dx 1 2 2>/dev/null | awk '/nvme|sd/{w=$(NF-1)} END{print \"await\", w+0}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.await > 20", "goto": "check_size"},
                      {"when": "output.await <= 20", "goto": "done_io_ok"}],
         "otherwise": "check_size",
         "cautions": ["checkpoint 慢多因写盘慢——大模型 ckpt 几十上百 GB，写到慢盘/网络存储会阻塞训练。"
                      "同步 save 会让所有 rank 等存完才继续"]},
        {"id": "check_size", "title": "看是否写到了慢存储",
         "cmd": "df -T $(dirname ${CKPT_DIR:-/tmp}) 2>/dev/null | awk 'NR==2{print $2}' | grep -ic 'nfs\\|cifs\\|fuse'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_network_storage"},
                      {"when": "output.value == 0", "goto": "done_local_slow"}],
         "otherwise": "escalate",
         "cautions": ["直接存到 NFS/对象存储会很慢——大 ckpt 应先写本地 NVMe 再异步上传；"
                      "同步存到远端会周期性卡训练"]},
     ],
     "dones": [
        {"id": "done_io_ok", "summary": "写盘不慢。checkpoint 慢另查(序列化/GPU→CPU 拷贝/是否 rank0 单点存)。"},
        {"id": "done_network_storage", "summary": "checkpoint 直接写网络存储导致慢。改为先写本地 NVMe 再异步上传；"
                                                 "或用分布式 checkpoint(各 rank 存自己分片)避免单点。"},
        {"id": "done_local_slow", "summary": "本地盘写 ckpt 仍慢，多为盘本身慢或 ckpt 太大。用更快 NVMe、"
                                            "开启异步/分片 checkpoint、降低保存频率或只存必要状态。"},
     ]},
    {**_A,
     "id": "aicomp.scheduling.gpu-fragmentation", "name": "GPU 调度碎片化排查",
     "taxonomy": "aicomp/scheduling/gpu-fragmentation",
     "symptom": "有空闲 GPU 但大任务调度不上/整机 GPU 凑不齐/碎片化",
     "checks": [
        {"id": "check_free", "title": "查空闲 GPU 分布",
         "cmd": "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | grep -c ' 0'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_pending"},
                      {"when": "output.value == 0", "goto": "done_all_busy"}],
         "otherwise": "check_pending",
         "cautions": ["单机有空闲卡但跨机凑不齐 8 卡=典型碎片化。整卡调度(要求同机多卡)对碎片敏感，"
                      "别只看总空闲数"]},
        {"id": "check_pending", "title": "查是否有 pending 的大任务",
         "cmd": "squeue 2>/dev/null | grep -ic 'PENDING\\|PD' || kubectl get pods -A 2>/dev/null | grep -ic Pending",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_fragmented"},
                      {"when": "output.value == 0", "goto": "done_no_demand"}],
         "otherwise": "escalate",
         "cautions": ["gang scheduling(整组一起调)缺失时，大任务的卡被小任务零散占用，永远凑不齐——"
                      "这是碎片化拖慢大任务的核心机制"]},
     ],
     "dones": [
        {"id": "done_all_busy", "summary": "GPU 全忙，非碎片化是真满载。扩容或排队等待。"},
        {"id": "done_fragmented", "summary": "有空闲卡但大任务 pending=碎片化。启用 gang scheduling(整组调度)、"
                                           "用 bin-packing 策略把小任务集中、或为大任务预留整机；碎片整理后大任务可调度。"},
        {"id": "done_no_demand", "summary": "有空闲卡但无 pending 任务=只是没需求，非调度问题。"},
     ]},
    {**_A,
     "id": "aicomp.fabric.ib-perf-degraded", "name": "InfiniBand 性能劣化排查",
     "taxonomy": "aicomp/fabric/ib-perf-degraded",
     "symptom": "IB 带宽低/RDMA 慢/多机训练通信慢/IB 有错误计数",
     "checks": [
        {"id": "check_rate", "title": "查 IB 端口速率是否降级",
         "cmd": "ibstat 2>/dev/null | grep -icE 'Rate: (10|25|40)\\b'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_errors"},
                      {"when": "output.value == 0", "goto": "check_errors"}],
         "otherwise": "check_errors",
         "cautions": ["IB 端口协商到低速率(如 HDR 卡跑成 EDR/FDR)=线缆/端口问题，带宽直接腰斩；"
                      "先确认速率对不对再查别的"]},
        {"id": "check_errors", "title": "查 IB 端口错误计数",
         "cmd": "perfquery 2>/dev/null | grep -icE 'SymbolError|LinkError|PortRcvErrors.*[1-9]' || ibstat 2>/dev/null | grep -c 'State: Active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_errors"},
                      {"when": "output.value == 0", "goto": "done_config"}],
         "otherwise": "escalate",
         "cautions": ["SymbolError/PortRcvErrors 增长=物理链路质量问题(线缆/光模块)；"
                      "RDMA 慢也可能是 GDR(GPUDirect RDMA)没开或 NUMA 亲和不对，非硬件"]},
     ],
     "dones": [
        {"id": "done_errors", "summary": "IB 有错误计数或速率降级。查线缆/光模块/端口，换线重插；"
                                        "速率不对核对两端与交换机的速率配置。"},
        {"id": "done_config", "summary": "IB 端口正常无错误，RDMA 慢多为配置问题。检查 GDR 是否启用、"
                                        "GPU 与 IB 卡的 NUMA 亲和(NCCL_IB_HCA/绑核)、MTU 是否一致。"},
     ]},
]
