"""H-push aicomp 域批量 spec（第三批）——显存/调度可见性/dataloader/MIG/fabricmanager/行重映射。"""

_A = {"capability_level": "read", "connector": "ssh", "facts": ["os.family", "gpu.driver.version"]}

SPECS = [
    {**_A,
     "id": "aicomp.gpu.cuda-oom", "name": "GPU 显存 OOM 排查",
     "taxonomy": "aicomp/gpu/cuda-oom",
     "symptom": "CUDA out of memory/训练或推理报显存不足/OOM 但 nvidia-smi 看着有余量",
     "checks": [
        {"id": "check_used", "title": "查显存占用最高的卡(百分比)",
         "cmd": "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | awk '{p=$1/$3*100; if(p>m)m=p} END{print int(m)}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 90", "goto": "check_procs"},
                      {"when": "output.value <= 90", "goto": "done_frag_or_spike"}],
         "otherwise": "check_procs",
         "cautions": ["CUDA OOM 未必是显存真满——PyTorch 缓存分配器会预留大块,碎片化会让'有余量却分不出连续块';"
                      "先看整体占用高不高再区分是真满还是碎片"]},
        {"id": "check_procs", "title": "看是否有多个进程共占一张卡",
         "cmd": "nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader 2>/dev/null | sort | uniq -c | sort -rn | head -1 | awk '{print $1}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1", "goto": "done_shared_gpu"},
                      {"when": "output.value <= 1", "goto": "done_real_oom"}],
         "otherwise": "escalate",
         "cautions": ["一张卡上跑了多个进程(别人的任务/上次没退干净的僵尸进程)会瓜分显存;"
                      "常见是训练崩了但进程没释放,显存一直被占,新任务就 OOM"]},
     ],
     "dones": [
        {"id": "done_frag_or_spike", "summary": "整体占用不算满却 OOM,多为碎片化或瞬时峰值。设 PYTORCH_CUDA_ALLOC_CONF"
                                             "(expandable_segments)缓解碎片、减小 batch/开梯度检查点降峰值;必要时空出卡重跑。"},
        {"id": "done_shared_gpu", "summary": "多个进程共占同卡瓜分显存。确认是否有残留僵尸进程占着(kill 掉释放)、"
                                          "或调度没做卡隔离让多任务撞车;用 CUDA_VISIBLE_DEVICES/调度器保证独占。"},
        {"id": "done_real_oom", "summary": "单进程独占仍显存满=模型/批次确实超显存。减小 batch size、开梯度检查点/ZeRO/"
                                        "混合精度、或模型并行拆到多卡;评估是否需要更大显存的卡。"},
     ]},
    {**_A,
     "id": "aicomp.scheduling.gpu-not-visible", "name": "进程/容器看不到 GPU 排查",
     "taxonomy": "aicomp/scheduling/gpu-not-visible",
     "symptom": "torch.cuda.is_available()=False/容器里 nvidia-smi 找不到卡/CUDA device not found",
     "checks": [
        {"id": "check_host", "title": "查宿主机能否看到 GPU",
         "cmd": "nvidia-smi -L 2>/dev/null | grep -c 'GPU '",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_visible_env"},
                      {"when": "output.value == 0", "goto": "done_host_no_gpu"}],
         "otherwise": "check_visible_env",
         "cautions": ["先分层:宿主机能不能看到卡→容器/进程能不能看到→框架能不能用。宿主机都看不到,"
                      "问题在驱动/硬件,不是容器配置"]},
        {"id": "check_visible_env", "title": "查是否被 CUDA_VISIBLE_DEVICES 屏蔽",
         "cmd": "env 2>/dev/null | grep -c 'CUDA_VISIBLE_DEVICES=$\\|CUDA_VISIBLE_DEVICES=-1\\|CUDA_VISIBLE_DEVICES=\"\"'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_masked_env"},
                      {"when": "output.value == 0", "goto": "done_container_runtime"}],
         "otherwise": "escalate",
         "cautions": ["CUDA_VISIBLE_DEVICES 设成空或 -1 会让进程看不到任何卡——常是脚本/调度器注入的,"
                      "程序里 is_available()=False 时先查这个环境变量,别急着怀疑驱动"]},
     ],
     "dones": [
        {"id": "done_host_no_gpu", "summary": "宿主机都看不到 GPU。查驱动是否加载(lsmod|grep nvidia)、卡是否掉总线(dmesg XID/"
                                           "fell off bus)、内核升级后驱动是否要重装;这是驱动/硬件层问题。"},
        {"id": "done_masked_env", "summary": "被 CUDA_VISIBLE_DEVICES 屏蔽(空/-1)。检查是谁设的(启动脚本/调度器/dockerfile),"
                                          "改成正确的卡号或取消屏蔽;这是'看不到卡'最常见的人为原因。"},
        {"id": "done_container_runtime", "summary": "宿主机可见且未被环境屏蔽,容器仍看不到=容器 GPU 直通没配好。确认用了"
                                                 "nvidia-container-runtime、docker 加 --gpus 或 k8s 声明 nvidia.com/gpu、device plugin 正常。"},
     ]},
    {**_A,
     "id": "aicomp.training.dataloader-bottleneck", "name": "数据加载瓶颈排查(GPU 空等数据)",
     "taxonomy": "aicomp/training/dataloader-bottleneck",
     "symptom": "GPU 利用率忽高忽低/训练慢但 GPU 没吃满/GPU 在等数据",
     "checks": [
        {"id": "check_util", "title": "查 GPU 利用率是否偏低",
         "cmd": "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | tr -dc '0-9\\n' | sort -n | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value < 60", "goto": "check_iowait"},
                      {"when": "output.value >= 60", "goto": "done_util_ok"}],
         "otherwise": "check_iowait",
         "cautions": ["GPU 利用率低+训练慢的经典原因是数据供不上:GPU 算得快,CPU 预处理/磁盘读数据跟不上,"
                      "GPU 只能空等。看利用率是否'锯齿状'(算一下等一下)"]},
        {"id": "check_iowait", "title": "看是否 CPU/IO 成瓶颈",
         "cmd": "top -bn1 2>/dev/null | awk '/%Cpu/{print \"iowait\", $10}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.iowait > 10", "goto": "done_io_bound"},
                      {"when": "output.iowait <= 10", "goto": "done_cpu_bound"}],
         "otherwise": "escalate",
         "cautions": ["iowait 高=卡在磁盘读数据(数据集在慢盘/网络存储、没做预取);iowait 低但 CPU 忙="
                      "卡在数据预处理(解码/增广)。两者解法不同"]},
     ],
     "dones": [
        {"id": "done_util_ok", "summary": "GPU 利用率不低。训练慢另查(通信/checkpoint/同步点/小 batch)。"},
        {"id": "done_io_bound", "summary": "IO 瓶颈:GPU 在等磁盘读数据。把数据集放本地 NVMe、用更高效格式(webdataset/lmdb)、"
                                        "加 DataLoader 预取(prefetch_factor)与 pin_memory;别让数据在慢盘/NFS 上拖训练。"},
        {"id": "done_cpu_bound", "summary": "CPU 预处理瓶颈:增广/解码吃满 CPU 供不上。调大 num_workers、把重预处理下沉"
                                         "(离线预处理/GPU 增广如 DALI)、精简增广流水线;让数据供给跟上 GPU 算力。"},
     ]},
    {**_A,
     "id": "aicomp.gpu.mig-misconfig", "name": "MIG 实例配置异常排查",
     "taxonomy": "aicomp/gpu/mig-misconfig",
     "symptom": "开了 MIG 但分不到实例/看不到 MIG 设备/任务调度不上 MIG 卡",
     "checks": [
        {"id": "check_mig_on", "title": "查是否启用了 MIG 模式",
         "cmd": "nvidia-smi --query-gpu=mig.mode.current --format=csv,noheader 2>/dev/null | grep -ic 'Enabled'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_instances"},
                      {"when": "output.value == 0", "goto": "done_mig_off"}],
         "otherwise": "check_instances",
         "cautions": ["MIG 模式切换需要 GPU 空闲且常要重置(有的卡要重启)才生效;'开了没生效'多因当时有进程占用"
                      "或没做 GPU reset"]},
        {"id": "check_instances", "title": "查是否已创建 MIG 实例",
         "cmd": "nvidia-smi mig -lgi 2>/dev/null | grep -cE 'MIG [0-9]+g'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_instances_ok"},
                      {"when": "output.value == 0", "goto": "done_no_instances"}],
         "otherwise": "escalate",
         "cautions": ["MIG 模式开了还得手动创建 GI(GPU Instance)+CI(Compute Instance)才有可用切片;"
                      "只开模式不建实例=任务看不到任何 MIG 设备"]},
     ],
     "dones": [
        {"id": "done_mig_off", "summary": "MIG 模式未启用。若需要切分:nvidia-smi -mig 1 开启(GPU 需空闲,可能要 reset/重启),"
                                       "再创建实例;若本不该用 MIG,则任务按整卡调度即可。"},
        {"id": "done_instances_ok", "summary": "MIG 模式开且已建实例。任务调度不上多为调度器/容器侧没正确暴露 MIG 设备"
                                            "(k8s 需 MIG 策略配置、CUDA_VISIBLE_DEVICES 用 MIG UUID);核对设备暴露与请求匹配。"},
        {"id": "done_no_instances", "summary": "MIG 模式开了但没创建实例,自然无可用切片。用 nvidia-smi mig -cgi/-cci 按需求"
                                            "创建 GI+CI(选合适的 profile),再让调度器发现这些实例。"},
     ]},
    {**_A,
     "id": "aicomp.fabric.fabricmanager-down", "name": "nvidia-fabricmanager 异常排查(NVSwitch)",
     "taxonomy": "aicomp/fabric/fabricmanager-down",
     "symptom": "NVSwitch 机型 GPU 用不了/CUDA 初始化失败/fabricmanager 未运行/NVLink 拓扑不成",
     "checks": [
        {"id": "check_fm", "title": "查 fabricmanager 服务是否在运行",
         "cmd": "systemctl is-active nvidia-fabricmanager 2>/dev/null | grep -ic '^active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_fm_down"},
                      {"when": "output.value > 0", "goto": "check_version"}],
         "otherwise": "check_version",
         "cautions": ["NVSwitch 机型(如 DGX/HGX)必须跑 fabricmanager 才能建立 GPU 间 NVLink 全互联;它没起,"
                      "GPU 可能直接不可用或 CUDA 初始化失败——这是这类机器的必查项"]},
        {"id": "check_version", "title": "看 fabricmanager 与驱动版本是否匹配",
         "cmd": "journalctl -u nvidia-fabricmanager --since '-10min' 2>/dev/null | grep -icE 'version mismatch|incompatible|failed to'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_version_mismatch"},
                      {"when": "output.value == 0", "goto": "done_fm_ok"}],
         "otherwise": "escalate",
         "cautions": ["fabricmanager 版本必须与 GPU 驱动严格匹配;驱动升级后没同步升 fabricmanager 会启动失败,"
                      "是升级后 GPU 集体不可用的常见坑"]},
     ],
     "dones": [
        {"id": "done_fm_down", "summary": "fabricmanager 未运行(NVSwitch 机型必需)。systemctl start 并设自启;"
                                       "若起不来看日志(多为版本不匹配或驱动问题),修复后 GPU 全互联才能建立。"},
        {"id": "done_version_mismatch", "summary": "fabricmanager 与驱动版本不匹配导致启动失败。安装与当前驱动完全一致版本的"
                                                "fabricmanager,重启服务;确保二者随驱动一起升级。"},
        {"id": "done_fm_ok", "summary": "fabricmanager 运行正常无版本问题。GPU 仍异常另查(单卡 XID/NVLink 物理链路/"
                                     "具体 CUDA 报错),非 fabric 服务层问题。"},
     ]},
    {**_A,
     "id": "aicomp.gpu.row-remap-pending", "name": "GPU 显存行重映射待处理排查",
     "taxonomy": "aicomp/gpu/row-remap-pending",
     "symptom": "nvidia-smi 提示 remapping pending/需要重启/显存出现 remap failure",
     "checks": [
        {"id": "check_pending", "title": "查是否有待处理的行重映射",
         "cmd": "nvidia-smi -q 2>/dev/null | grep -icE 'Remapping Pending\\s*:\\s*Yes|Pending\\s*:\\s*Yes'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_failure"},
                      {"when": "output.value == 0", "goto": "done_no_pending"}],
         "otherwise": "check_failure",
         "cautions": ["A100+ 用行重映射把坏的显存行替换为备用行,以隔离显存故障;'Pending: Yes'表示已标记但"
                      "需要一次 GPU 重置/重启才真正生效——不重置,坏行还在用,可能 ECC 报错或崩"]},
        {"id": "check_failure", "title": "看是否有重映射失败(备用行耗尽)",
         "cmd": "nvidia-smi -q 2>/dev/null | grep -icE 'Remapping Failure|Failure Occurred\\s*:\\s*Yes'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_remap_failed"},
                      {"when": "output.value == 0", "goto": "done_need_reset"}],
         "otherwise": "escalate",
         "cautions": ["Remapping Failure=备用行用尽或重映射失败,说明显存物理损坏已超出可修复范围——"
                      "这张卡通常需要 RMA 更换,别再投产跑关键任务"]},
     ],
     "dones": [
        {"id": "done_no_pending", "summary": "无待处理行重映射。显存相关异常另查(ECC 计数/XID/具体报错)。"},
        {"id": "done_remap_failed", "summary": "行重映射失败(备用行耗尽,显存物理损坏)。将该卡下线报修/RMA,"
                                            "别再承载关键任务;记录序列号与错误供厂商核查。"},
        {"id": "done_need_reset", "summary": "有待处理重映射但未失败。安排窗口对该卡做 GPU reset(nvidia-smi -r,需无进程占用)"
                                          "或重启节点让重映射生效;生效后确认 Pending 变 No、观察 ECC 是否稳定。"},
     ]},
]
