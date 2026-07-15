"""H-3 network 域批量 spec（第一批）——只用语法树已覆盖前缀，cisco_ios+huawei_vrp 双平台。

命令前缀均在 tools/syntax/{cisco_ios,huawei_vrp}.yaml 已覆盖列表内，S6 零风险。
解析器用 generic 族（对 show/display 文本做计数/表格），避免逐厂商 ntc 模板成本。
"""

_COMMON = {"network": True, "devices": ["cisco_ios", "huawei_vrp"],
           "connector": "netconf", "capability_level": "read"}

SPECS = [
    {**_COMMON,
     "id": "network.switching.mac-flapping", "name": "MAC 地址漂移排查",
     "taxonomy": "network/switching/mac-flapping",
     "symptom": "MAC 地址漂移/同一 MAC 在多个端口反复学习/日志报 mac move",
     "checks": [
        {"id": "check_log", "title": "查日志有无 MAC 漂移告警",
         "cmds": {"cisco_ios": "show logging | include MAC.*flap|MACFLAP",
                  "huawei_vrp": "display logbuffer | include MAC|flapping"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_mac"},
                      {"when": "output.value == 0", "goto": "done_no_flap"}],
         "otherwise": "check_mac",
         "cautions": ["MAC 漂移几乎总是二层环路或双上行未做好聚合的征兆——先怀疑拓扑，别急着清 MAC 表"]},
        {"id": "check_mac", "title": "看该 MAC 当前学习在哪些端口",
         "cmds": {"cisco_ios": "show mac address-table | include DYNAMIC",
                  "huawei_vrp": "display mac-address | include Dynamic"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_loop_suspect"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["同 MAC 在两个端口间反复跳=环路；若一端是服务器双网卡，多为 bond 模式配错"
                      "（两口都在转发同一 MAC）"]},
     ],
     "dones": [
        {"id": "done_no_flap", "summary": "无 MAC 漂移告警。若仍偶发丢包，转查接口错包或链路抖动。"},
        {"id": "done_loop_suspect", "summary": "存在 MAC 漂移，高度疑似二层环路或双上行配置问题。"
                                               "核对 STP 是否正常收敛、服务器 bond 模式与交换机侧聚合是否匹配；"
                                               "定位漂移的两个端口后从拓扑上消除环路。"},
     ]},
    {**_COMMON,
     "id": "network.switching.port-err-disabled", "name": "端口 err-disabled 排查",
     "taxonomy": "network/switching/port-err-disabled",
     "symptom": "端口被自动关闭/err-disabled/接口 down 且不自动恢复",
     "checks": [
        {"id": "check_status", "title": "查有无 err-disabled 端口",
         "cmds": {"cisco_ios": "show interfaces status | include err-disabled|errdisable",
                  "huawei_vrp": "display interface brief | include *down|ERROR"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_reason"},
                      {"when": "output.value == 0", "goto": "done_none"}],
         "otherwise": "check_reason",
         "cautions": ["err-disabled 是保护机制不是故障——端口触发了某种违规(风暴/BPDU/安全)被主动关，"
                      "直接 shut/no shut 会再次触发，必须先找原因"]},
        {"id": "check_reason", "title": "查触发原因",
         "cmds": {"cisco_ios": "show logging | include err-disable|psecure|bpduguard|storm",
                  "huawei_vrp": "display logbuffer | include error-down|security"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_found_reason"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["常见触发：port-security 学到超限 MAC、BPDU Guard 收到 BPDU(接了交换机)、"
                      "storm-control 超阈值。对症解决而非盲目恢复端口"]},
     ],
     "dones": [
        {"id": "done_none", "summary": "无 err-disabled 端口。接口 down 另有原因(物理/对端/管理关闭)。"},
        {"id": "done_found_reason", "summary": "找到 err-disabled 触发原因。对症处理：安全违规查接入设备、"
                                               "BPDU 违规查是否误接交换机、风暴查环路；处理后再恢复端口"
                                               "（或配 errdisable recovery 自动恢复）。"},
     ]},
    {**_COMMON,
     "id": "network.physical.link-flap", "name": "接口 up/down 抖动排查",
     "taxonomy": "network/physical/link-flap",
     "symptom": "接口反复 up down/链路抖动/日志刷 line protocol changed",
     "checks": [
        {"id": "check_flap_log", "title": "查接口状态变化日志频率",
         "cmds": {"cisco_ios": "show logging | include changed state|LINK-3|LINEPROTO",
                  "huawei_vrp": "display logbuffer | include LINK_STATE|link is"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 10", "goto": "check_errors"},
                      {"when": "output.value <= 10", "goto": "done_stable"}],
         "otherwise": "check_errors",
         "cautions": ["翻动次数结合时间窗看——一天翻两次和一分钟翻十次性质完全不同"]},
        {"id": "check_errors", "title": "看该接口物理层错误",
         "cmds": {"cisco_ios": "show interfaces | include error|CRC|reset",
                  "huawei_vrp": "display interface | include errors|CRC"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_physical"},
                      {"when": "output.value == 0", "goto": "done_negotiation"}],
         "otherwise": "escalate",
         "cautions": ["有 CRC/error=物理层问题(线/光模块/接口)；无错误却抖多为双工/速率协商不一致"
                      "或对端节能(EEE)引起"]},
     ],
     "dones": [
        {"id": "done_stable", "summary": "接口状态变化不频繁，基本稳定。若业务仍偶断，查上层(路由/STP)。"},
        {"id": "done_physical", "summary": "接口抖动伴物理层错误。排查顺序：换线 → 换光模块 → 换接口/板卡；"
                                           "光口用 show transceiver 看收发光功率是否越界。"},
        {"id": "done_negotiation", "summary": "抖动无物理错误，多为速率/双工协商不一致或对端 EEE 节能。"
                                              "两端固定同样的速率/双工，或关闭 EEE 后观察。"},
     ]},
    {**_COMMON,
     "id": "network.reachability.latency-high", "name": "网络延迟高逐跳定位",
     "taxonomy": "network/reachability/latency-high",
     "symptom": "访问慢/rtt 高/网络延迟大不知道慢在哪一跳",
     "checks": [
        {"id": "ping_target", "title": "先测到目标的连通与丢包",
         "cmds": {"cisco_ios": "ping 8.8.8.8 repeat 20",
                  "huawei_vrp": "ping -c 20 8.8.8.8"},
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.loss >= 50", "goto": "done_unreachable"},
                      {"when": "output.loss < 50", "goto": "trace_hops"}],
         "otherwise": "trace_hops",
         "cautions": ["设备 CPU 处理的 ping 会被低优先级排队，偶发大 rtt 不代表转发面慢——"
                      "关注平均值与丢包，别被个别尖刺误导"]},
        {"id": "trace_hops", "title": "逐跳定位延迟拐点",
         "cmds": {"cisco_ios": "traceroute 8.8.8.8",
                  "huawei_vrp": "tracert 8.8.8.8"},
         "parser": "generic/table-v1",
         "branches": [{"when": "output.row_count > 0", "goto": "done_hop_found"}],
         "otherwise": "escalate",
         "cautions": ["找延迟'跳变'的那一跳：从某跳起 rtt 阶跃上升=瓶颈在该跳到上一跳之间。"
                      "但中间设备对 traceroute 探测限速会造成假高，最后一跳延迟才最可信"]},
     ],
     "dones": [
        {"id": "done_unreachable", "summary": "到目标丢包严重(≥50%)，这已不是'延迟高'而是'通不了'——"
                                              "转按丢包/可达性排查(逐跳 traceroute 看断点)，而非纠结延迟数值。"},
        {"id": "done_hop_found", "summary": "逐跳数据已获取。定位延迟阶跃出现的那一跳，其上游链路为瓶颈；"
                                           "若阶跃跳是运营商网络则需联系 ISP，内网跳则查该段链路拥塞/绕行。"},
     ]},
    {**_COMMON,
     "id": "network.routing.default-route-missing", "name": "默认路由丢失排查",
     "taxonomy": "network/routing/default-route-missing",
     "symptom": "出不了外网/默认路由没了/0.0.0.0 路由不见了",
     "checks": [
        {"id": "check_default", "title": "查是否存在默认路由",
         "cmds": {"cisco_ios": "show ip route 0.0.0.0",
                  "huawei_vrp": "display ip routing-table 0.0.0.0"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "check_source"},
                      {"when": "output.value > 0", "goto": "done_has_default"}],
         "otherwise": "check_source",
         "cautions": ["默认路由可能来自静态、也可能来自动态协议(BGP/OSPF)通告——丢失原因因来源而异"]},
        {"id": "check_source", "title": "看默认路由本该从哪来",
         "cmds": {"cisco_ios": "show running-config | include ip route 0.0.0.0|default-information",
                  "huawei_vrp": "display current-configuration | include ip route-static 0.0.0.0|default-route"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_static_gone"},
                      {"when": "output.value == 0", "goto": "done_dynamic_gone"}],
         "otherwise": "escalate",
         "cautions": ["配了静态默认路由却不在路由表=下一跳不可达被撤(接口down/递归失败)；"
                      "配置里没有=依赖动态协议但通告方停了"]},
     ],
     "dones": [
        {"id": "done_has_default", "summary": "默认路由存在。出不去外网另有原因(NAT/ACL/上游)，转查这些。"},
        {"id": "done_static_gone", "summary": "配了静态默认路由但未生效——下一跳不可达导致路由被撤。"
                                             "检查下一跳接口是否 up、下一跳地址是否可达(递归路由是否解析)。"},
        {"id": "done_dynamic_gone", "summary": "无静态默认路由，依赖动态协议通告的默认路由消失了。"
                                              "到通告方(上游路由器)确认其是否仍在发默认路由、邻居是否正常。"},
     ]},
    {**_COMMON,
     "id": "network.traffic.broadcast-storm", "name": "广播风暴排查",
     "taxonomy": "network/traffic/broadcast-storm",
     "symptom": "广播包异常多/网络整体变慢/交换机 CPU 高/疑似风暴",
     "checks": [
        {"id": "check_counters", "title": "查接口广播/组播包计数",
         "cmds": {"cisco_ios": "show interfaces counters | include broadcast|Broadcast",
                  "huawei_vrp": "display interface | include broadcast|Broadcast"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_stp"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "check_stp",
         "cautions": ["广播计数是累计值，要看增速；短时间暴增才是风暴。风暴时先隔离(关可疑端口)止血，再排根因"]},
        {"id": "check_stp", "title": "看 STP 是否异常(环路征兆)",
         "cmds": {"cisco_ios": "show spanning-tree | include FWD|BLK|Topology",
                  "huawei_vrp": "display stp | include FORWARDING|DISCARDING|TC"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_stp_loop"},
                      {"when": "output.value == 0", "goto": "done_source_host"}],
         "otherwise": "escalate",
         "cautions": ["频繁 TC(拓扑变更)或本该 BLOCK 的口在 FWD=环路。风暴的两大来源：二层环路、"
                      "或某主机故障狂发广播——STP 异常指向前者"]},
     ],
     "dones": [
        {"id": "done_stp_loop", "summary": "STP 异常，广播风暴源于二层环路。定位环路(哪两条路径成环)，"
                                           "确认 STP 配置(是否有端口被误配 BPDU filter/portfast 导致不参与计算)，消除环路。"},
        {"id": "done_source_host", "summary": "STP 正常，风暴可能源于某主机狂发广播(网卡故障/病毒/错误软件)。"
                                              "按端口广播计数定位源端口，隔离该主机排查。"},
     ]},
]
