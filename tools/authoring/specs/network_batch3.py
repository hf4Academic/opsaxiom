"""H-3 network 域批量 spec（第三批，收尾）。"""

_C = {"network": True, "devices": ["cisco_ios", "huawei_vrp"],
      "connector": "netconf", "capability_level": "read"}

SPECS = [
    {**_C,
     "id": "network.reachability.arp-storm", "name": "ARP 风暴排查",
     "taxonomy": "network/reachability/arp-storm",
     "symptom": "ARP 报文异常多/CPU 被 ARP 打高/网关响应慢",
     "checks": [
        {"id": "check_arp_count", "title": "查 ARP 表项规模",
         "cmds": {"cisco_ios": "show ip arp | count Internet",
                  "huawei_vrp": "display arp | include Dynamic"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 5000", "goto": "check_cpu"},
                      {"when": "output.value <= 5000", "goto": "done_normal_scale"}],
         "otherwise": "check_cpu",
         "cautions": ["ARP 表项数只是规模指标，风暴的关键是 ARP 报文速率——表大不等于风暴，"
                      "但大表 + CPU 高才是风暴特征。别把大二层的正常规模误判成风暴"]},
        {"id": "check_cpu", "title": "查 CPU 是否被 ARP 处理打高",
         "cmds": {"cisco_ios": "show processes cpu | include ARP|IP Input",
                  "huawei_vrp": "display cpu-usage | include ARP|SOCK"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_arp_storm"},
                      {"when": "output.value == 0", "goto": "done_high_scale_ok"}],
         "otherwise": "escalate",
         "cautions": ["ARP 风暴常源于：环路放大广播、扫描器扫全网段、或代理 ARP 配置不当。"
                      "止血可对接入口做 ARP 限速(rate-limit)，根因还是查环路/扫描源"]},
     ],
     "dones": [
        {"id": "done_normal_scale", "summary": "ARP 表规模正常。网关慢另查(转发/上行/会话)。"},
        {"id": "done_high_scale_ok", "summary": "表大但 CPU 未被 ARP 打高，是正常的大二层规模。"
                                               "长期建议拆分广播域缩小 ARP 表，非紧急。"},
        {"id": "done_arp_storm", "summary": "ARP 表大且 CPU 被处理打高=ARP 风暴。定位报文源(哪个接入口"
                                           "涌入)，先做 ARP 限速止血；排查是环路广播放大还是主机异常/扫描。"},
     ]},
    {**_C,
     "id": "network.traffic.qos-drops", "name": "QoS 队列丢包排查",
     "taxonomy": "network/traffic/qos-drops",
     "symptom": "某类流量丢包/QoS 队列 drop/语音视频卡但带宽没满",
     "checks": [
        {"id": "check_policy", "title": "查 QoS 策略队列丢包",
         "cmds": {"cisco_ios": "show policy-map interface | include drop|Drop",
                  "huawei_vrp": "display qos | include drop|discard"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_queue"},
                      {"when": "output.value == 0", "goto": "done_no_drop"}],
         "otherwise": "check_queue",
         "cautions": ["QoS 丢包发生在带宽没满时=某个队列的配额(bandwidth/priority)太小，"
                      "不是链路拥塞——这是 QoS 配置问题不是容量问题"]},
        {"id": "check_queue", "title": "看是哪类队列在丢",
         "cmds": {"cisco_ios": "show policy-map interface | include Class|priority|bandwidth",
                  "huawei_vrp": "display traffic-policy | include queue|cir"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_queue_config"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["优先级队列(priority/LLQ)超过配额也会被丢——语音流超了 priority 带宽照样丢，"
                      "别以为进了优先队列就绝对不丢"]},
     ],
     "dones": [
        {"id": "done_no_drop", "summary": "QoS 队列无丢包。业务卡另查(端到端时延/抖动/对端)。"},
        {"id": "done_queue_config", "summary": "定位到丢包的队列。核对该类流量的队列配额是否够"
                                              "(bandwidth/priority 值)；配额不足则调大，或核对分类(class-map)是否把流量"
                                              "错分到了小队列。"},
     ]},
    {**_C,
     "id": "network.security-policy.nat-session-full", "name": "NAT 会话表满排查",
     "taxonomy": "network/security-policy/nat-session-full",
     "symptom": "新连接建不了/NAT 转换失败/会话表满/上网时断",
     "checks": [
        {"id": "check_sessions", "title": "查 NAT 会话数",
         "cmds": {"cisco_ios": "show ip nat translations | count",
                  "huawei_vrp": "display nat session | include total|Total"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 50000", "goto": "check_top"},
                      {"when": "output.value <= 50000", "goto": "done_not_full"}],
         "otherwise": "check_top",
         "cautions": ["NAT 会话有硬上限，满了新连接直接建不了；PAT(端口复用)下单公网 IP 也只有 6 万余端口，"
                      "高并发环境容易撞"]},
        {"id": "check_top", "title": "看是否单主机占用异常多会话",
         "cmds": {"cisco_ios": "show ip nat translations | include tcp|udp",
                  "huawei_vrp": "display nat session | include Src"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_found_hog"},
                      {"when": "output.value == 0", "goto": "done_scale"}],
         "otherwise": "escalate",
         "cautions": ["单主机会话暴多常因 P2P/爬虫/病毒/连接泄漏(不复用连接)——先定位这类源；"
                      "全局都高则是真并发大，需扩公网 IP 或缩短会话老化时间"]},
     ],
     "dones": [
        {"id": "done_not_full", "summary": "NAT 会话未满。上网时断另查(路由/线路/上游)。"},
        {"id": "done_found_hog", "summary": "有主机占用会话异常多。定位该主机排查(P2P/病毒/连接泄漏)；"
                                           "临时可对其限制会话数，根治在主机侧。"},
        {"id": "done_scale", "summary": "会话普遍高=真实并发大。缓解：缩短 NAT 会话老化时间(尤其 TCP time-wait)、"
                                       "增加公网 IP 扩大 PAT 端口池、或分流。"},
     ]},
    {**_C,
     "id": "network.physical.optic-power-degrading", "name": "光模块光功率劣化趋势排查",
     "taxonomy": "network/physical/optic-power-degrading",
     "symptom": "光功率下降/接口偶发错包/怀疑光模块老化",
     "checks": [
        {"id": "check_power", "title": "读光模块收发光功率",
         "cmds": {"cisco_ios": "show interfaces transceiver | include Rx|Tx|dBm",
                  "huawei_vrp": "display transceiver | include Rx|Tx|Power"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_errors"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "check_errors",
         "cautions": ["接收光功率(Rx)低于模块灵敏度阈值会误码；不同模块阈值不同(单模/多模/长距)，"
                      "要对照该模块的 DDM 告警门限判断，不是绝对值越大越好"]},
        {"id": "check_errors", "title": "看是否已伴随错包",
         "cmds": {"cisco_ios": "show interfaces | include CRC|input errors",
                  "huawei_vrp": "display interface | include CRC|errors"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_power_bad"},
                      {"when": "output.value == 0", "goto": "done_power_watch"}],
         "otherwise": "escalate",
         "cautions": ["光功率接近门限但还没错包=劣化早期，此时更换成本最低；等到大量 CRC 才换已影响业务"]},
     ],
     "dones": [
        {"id": "done_power_bad", "summary": "光功率异常且已有错包。立即处置：先清洁光纤接头(脏污是首因)，"
                                           "无改善则换光模块，再不行查光纤链路衰减(距离/熔接点)。"},
        {"id": "done_power_watch", "summary": "光功率偏离但暂无错包，处于劣化早期。纳入趋势监控，"
                                             "择机(业务低峰)清洁接头或预防性更换，避免恶化到影响业务。"},
     ]},
    {**_C,
     "id": "network.routing.route-flapping", "name": "路由震荡排查",
     "taxonomy": "network/routing/route-flapping",
     "symptom": "路由表频繁变动/某前缀时有时无/BGP 反复收发路由",
     "checks": [
        {"id": "check_log", "title": "查路由/邻居震荡日志",
         "cmds": {"cisco_ios": "show logging | include BGP|OSPF|ADJCHANGE|flap",
                  "huawei_vrp": "display logbuffer | include BGP|OSPF|Neighbor"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 10", "goto": "check_neighbor"},
                      {"when": "output.value <= 10", "goto": "done_stable"}],
         "otherwise": "check_neighbor",
         "cautions": ["路由震荡多由底层链路/邻居抖动引起——先看是不是接口 flap 带动了协议震荡，"
                      "根在物理层"]},
        {"id": "check_neighbor", "title": "查邻居稳定性",
         "cmds": {"cisco_ios": "show ip bgp summary | include never|00:0|00:1",
                  "huawei_vrp": "display bgp peer | include 00:0|00:1"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_neighbor_flap"},
                      {"when": "output.value == 0", "goto": "done_route_only"}],
         "otherwise": "escalate",
         "cautions": ["邻居 uptime 很短(几分钟内)=邻居在反复重建；BGP 可用 route dampening 抑制震荡"
                      "但那是缓解，根因在链路/邻居"]},
     ],
     "dones": [
        {"id": "done_stable", "summary": "路由日志无频繁震荡。前缀时有时无另查(通告策略/汇总)。"},
        {"id": "done_neighbor_flap", "summary": "邻居在反复重建导致路由震荡。定位邻居抖动根因"
                                              "(链路 flap/超时配置/MTU)；先稳住邻居，必要时配 dampening 抑制扩散。"},
        {"id": "done_route_only", "summary": "邻居稳定但路由仍变，多为通告侧策略震荡或某前缀源不稳。"
                                            "到通告方查该前缀的产生源(重分发/汇总条件)是否在抖动。"},
     ]},
    {**_C,
     "id": "network.config-mgmt.config-drift", "name": "设备配置漂移排查",
     "taxonomy": "network/config-mgmt/config-drift",
     "symptom": "设备配置被改过/和基线不一致/运行配置与保存配置不同",
     "checks": [
        {"id": "check_unsaved", "title": "查运行配置是否未保存",
         "cmds": {"cisco_ios": "show running-config | include Last configuration",
                  "huawei_vrp": "display current-configuration | include time"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_baseline"},
                      {"when": "output.value == 0", "goto": "check_baseline"}],
         "otherwise": "check_baseline",
         "cautions": ["运行配置(running)改了没保存(startup)，重启就丢——先确认改动是否有意，"
                      "有意则保存，无意则回退"]},
        {"id": "check_baseline", "title": "抽查关键配置项是否偏离基线",
         "cmds": {"cisco_ios": "show running-config | include enable secret|aaa|snmp-server community",
                  "huawei_vrp": "display current-configuration | include aaa|snmp-agent community"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_baseline_gap"},
                      {"when": "output.value > 0", "goto": "done_config_present"}],
         "otherwise": "escalate",
         "cautions": ["明文 community/弱认证是安全基线红线；抽查这些项能快速发现被降级的安全配置"]},
     ],
     "dones": [
        {"id": "done_baseline_gap", "summary": "关键安全配置项缺失或被改。对照基线补齐(认证/SNMP/AAA)；"
                                             "查配置变更记录(谁在什么时候改的)，走变更流程恢复。"},
        {"id": "done_config_present", "summary": "抽查项存在。全量比对建议用配置管理工具对 running-config"
                                               "与基线做 diff；本 Skill 只做快速抽检并提醒保存未保存的改动。"},
     ]},
]
