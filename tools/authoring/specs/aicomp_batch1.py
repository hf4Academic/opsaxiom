"""H-6 aicomp 域批量 spec（第一批）——GPU/NVLink/PCIe/NCCL，linux 平台。"""

_A = {"capability_level": "read", "connector": "ssh", "facts": ["os.family", "gpu.driver.version"]}

SPECS = [
    {**_A,
     "id": "aicomp.gpu.pcie-downgrade", "name": "GPU PCIe 链路降速排查",
     "taxonomy": "aicomp/gpu/pcie-downgrade",
     "symptom": "GPU 数据传输慢/PCIe 从 x16 降到 x4/H2D 带宽低",
     "checks": [
        {"id": "check_width", "title": "查 PCIe 当前链路宽度",
         "cmd": "nvidia-smi --query-gpu=pcie.link.width.current --format=csv,noheader 2>/dev/null | sort -n | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value < 16", "goto": "check_load"},
                      {"when": "output.value >= 16", "goto": "done_width_ok"}],
         "otherwise": "check_load",
         "cautions": ["空载时 PCIe 会主动降速省电(ASPM)，此时 x4/x8 是正常的——必须在有负载时看当前宽度，"
                      "别把节能降速误判成硬件故障"]},
        {"id": "check_load", "title": "确认 GPU 是否在负载中",
         "cmd": "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | tr -dc '0-9\\n' | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 50", "goto": "done_real_downgrade"},
                      {"when": "output.value <= 50", "goto": "done_maybe_aspm"}],
         "otherwise": "escalate",
         "cautions": ["降速的真实危害在多卡训练的 all-reduce/参数同步阶段——H2D/D2D 带宽腰斩会拖慢整个训练"]},
     ],
     "dones": [
        {"id": "done_width_ok", "summary": "PCIe 链路宽度正常(x16)。传输慢另查(NUMA 亲和/拷贝方式/pinned memory)。"},
        {"id": "done_real_downgrade", "summary": "负载中仍降速=真实链路问题。排查：GPU 没插紧/金手指氧化、"
                                               "PCIe 插槽或转接卡故障、BIOS 里 PCIe 代数/lane 配置。重新插拔+清洁是第一步。"},
        {"id": "done_maybe_aspm", "summary": "GPU 空载，当前降速可能只是 ASPM 节能。加负载(跑个 bandwidthTest)"
                                           "再看宽度是否恢复 x16；恢复则正常，仍降速才是硬件问题。"},
     ]},
    {**_A,
     "id": "aicomp.fabric.nvlink-error", "name": "NVLink 错误/降级排查",
     "taxonomy": "aicomp/fabric/nvlink-error",
     "symptom": "NVLink 报错/卡间带宽低/nvidia-smi nvlink 有错误计数",
     "checks": [
        {"id": "check_nvlink_err", "title": "查 NVLink 错误计数",
         "cmd": "nvidia-smi nvlink -e 2>/dev/null | grep -icE 'Replay|Recovery|CRC.*[1-9]'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_status"},
                      {"when": "output.value == 0", "goto": "done_no_err"}],
         "otherwise": "check_status",
         "cautions": ["Replay/Recovery 错误偶发可自愈，但持续增长会降带宽；CRC 错误多为物理链路(NVLink 桥接/背板)"]},
        {"id": "check_status", "title": "查 NVLink 链路是否 up",
         "cmd": "nvidia-smi nvlink -s 2>/dev/null | grep -ic 'inactive\\|Link is down'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_link_down"},
                      {"when": "output.value == 0", "goto": "done_err_only"}],
         "otherwise": "escalate",
         "cautions": ["NVLink 掉链路会让卡间通信回退到 PCIe(慢一个数量级)，多卡训练性能断崖——"
                      "NCCL 慢先排查 NVLink 是否全 up"]},
     ],
     "dones": [
        {"id": "done_no_err", "summary": "NVLink 无错误计数。卡间慢另查(NCCL 配置/拓扑/PCIe)。"},
        {"id": "done_link_down", "summary": "有 NVLink 链路 down，通信回退 PCIe 导致性能断崖。检查 NVLink"
                                          "桥接器/背板连接，重新插拔；确认 nvidia-fabricmanager 服务正常(NVSwitch 机型)。"},
        {"id": "done_err_only", "summary": "链路 up 但有错误计数。偶发可观察，持续增长则查物理链路质量；"
                                          "错误多时带宽会降，影响 all-reduce 性能。"},
     ]},
    {**_A,
     "id": "aicomp.gpu.clocks-locked", "name": "GPU 时钟被锁/降频排查",
     "taxonomy": "aicomp/gpu/clocks-locked",
     "symptom": "GPU 算力上不去/时钟被锁在低频/性能不达标",
     "checks": [
        {"id": "check_throttle", "title": "查降频原因标志",
         "cmd": "nvidia-smi -q -d PERFORMANCE 2>/dev/null | grep -icE 'SW Thermal.*Active|HW Thermal.*Active|SW Power.*Active|HW Slowdown.*Active'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_temp"},
                      {"when": "output.value == 0", "goto": "check_locked"}],
         "otherwise": "check_temp",
         "cautions": ["nvidia-smi 的 clocks throttle reasons 直接告诉你为啥降频——热/功耗/硬件慢速。"
                      "别猜，看这个字段"]},
        {"id": "check_temp", "title": "查温度是否触发热降频",
         "cmd": "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader 2>/dev/null | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 83", "goto": "done_thermal"},
                      {"when": "output.value <= 83", "goto": "done_power_limit"}],
         "otherwise": "escalate",
         "cautions": ["多数卡 83-90℃ 开始热降频；温度高先查散热(风道/积灰/风扇/机房温度)，"
                      "别急着怀疑卡坏"]},
        {"id": "check_locked", "title": "查是否被 nvidia-smi -lgc 手动锁频",
         "cmd": "nvidia-smi --query-gpu=clocks.applications.graphics --format=csv,noheader 2>/dev/null | tr -dc '0-9\\n' | sort -n | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_manual_lock"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["有人跑过 nvidia-smi -lgc/-ac 锁频后忘了 -rgc 恢复，是'莫名降频'的常见人为原因"]},
     ],
     "dones": [
        {"id": "done_thermal", "summary": "热降频。查散热：清积灰、检查风扇转速、机房进风温度、GPU 风道是否被挡；"
                                         "降温后时钟自动恢复。"},
        {"id": "done_power_limit", "summary": "非热主导，多为功耗墙降频。查 power limit(nvidia-smi -pl)是否被调低、"
                                            "整机供电是否不足；按卡规格恢复功耗上限。"},
        {"id": "done_manual_lock", "summary": "时钟被手动锁定(应用时钟被设过)。用 nvidia-smi -rgc 恢复默认时钟、"
                                            "-rac 恢复应用时钟；确认没有开机脚本在自动锁频。"},
     ]}
]
