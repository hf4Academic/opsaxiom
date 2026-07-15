"""H-push network 域批量 spec（第五批，收官）——OSPF MTU/MAC表满/ARP解析/输入丢包。"""

_C = {"network": True, "devices": ["cisco_ios", "huawei_vrp"],
      "connector": "netconf", "capability_level": "read"}

SPECS = [
    {**_C,
     "id": "network.routing.ospf-mtu-mismatch", "name": "OSPF 邻居卡 ExStart(MTU 不匹配)排查",
     "taxonomy": "network/routing/ospf-mtu-mismatch",
     "symptom": "OSPF 邻居卡在 ExStart/Exchange 建不成 Full/邻居反复重建/MTU 不一致",
     "checks": [
        {"id": "check_stuck", "title": "查是否有邻居卡在 ExStart/Exchange",
         "cmds": {"cisco_ios": "show ip ospf neighbor | include EXSTART|EXCHANGE",
                  "huawei_vrp": "display ospf peer | include ExStart|Exchange"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_mtu"},
                      {"when": "output.value == 0", "goto": "done_not_stuck"}],
         "otherwise": "check_mtu",
         "cautions": ["OSPF 邻居卡 ExStart/Exchange 建不成 Full 的最经典原因就是两端接口 MTU 不一致——"
                      "DBD 报文交换时因 MTU 对不上被拒,卡住不前;先怀疑 MTU 再查别的"]},
        {"id": "check_mtu", "title": "查接口 MTU 配置",
         "cmds": {"cisco_ios": "show ip ospf interface | include MTU",
                  "huawei_vrp": "display ospf interface | include MTU"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_mtu_check"},
                      {"when": "output.value == 0", "goto": "done_other_param"}],
         "otherwise": "escalate",
         "cautions": ["核对两端接口 MTU 必须一致;临时可在接口下配 ip ospf mtu-ignore 让 OSPF 忽略 MTU 检查绕过,"
                      "但那是权宜——根治要把两端 MTU 改一致,否则大 LSA 仍可能出问题"]},
     ],
     "dones": [
        {"id": "done_not_stuck", "summary": "无邻居卡 ExStart/Exchange。OSPF 邻居问题另查(Init/2-Way 卡则是 hello/网络类型/"
                                         "DR 选举;建不起则查 area/认证/timer)。"},
        {"id": "done_mtu_check", "summary": "邻居卡 ExStart 且能读到 MTU=高度疑似 MTU 不匹配。核对两端接口 MTU 改一致;"
                                         "应急可配 mtu-ignore 先建起邻居,但要尽快统一 MTU 根治。"},
        {"id": "done_other_param", "summary": "卡 ExStart 但 MTU 信息不足以判定。逐项核对两端:MTU、OSPF 区域类型、"
                                           "认证、以及是否有 ACL/防火墙挡了 OSPF 组播(224.0.0.5/6)。"},
     ]},
    {**_C,
     "id": "network.switching.mac-table-full", "name": "MAC 地址表满排查",
     "taxonomy": "network/switching/mac-table-full",
     "symptom": "学不了新 MAC/大量未知单播泛洪/MAC 表满/接入新设备不通",
     "checks": [
        {"id": "check_count", "title": "查 MAC 表项规模",
         "cmds": {"cisco_ios": "show mac address-table count | include Dynamic|Total",
                  "huawei_vrp": "display mac-address total-number"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 8000", "goto": "check_port"},
                      {"when": "output.value <= 8000", "goto": "done_not_full"}],
         "otherwise": "check_port",
         "cautions": ["MAC 表满后学不到新地址,目的为新地址的帧只能全端口泛洪(未知单播泛洪),既浪费带宽又是安全隐患;"
                      "表项异常暴涨常因二层环路或 MAC 泛洪攻击"]},
        {"id": "check_port", "title": "看是否某端口学到海量 MAC",
         "cmds": {"cisco_ios": "show mac address-table | include DYNAMIC",
                  "huawei_vrp": "display mac-address | include dynamic"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 5000", "goto": "done_flood_attack"},
                      {"when": "output.value <= 5000", "goto": "done_real_scale"}],
         "otherwise": "escalate",
         "cautions": ["单端口学到成千上万 MAC=典型 MAC 泛洪(攻击/环路/下挂大量虚拟机);port-security 限制每端口"
                      "MAC 数可止血;正常大二层则是规模到了,需评估表容量"]},
     ],
     "dones": [
        {"id": "done_not_full", "summary": "MAC 表未满。接入不通另查(VLAN/端口状态/STP block/物理链路)。"},
        {"id": "done_flood_attack", "summary": "单端口学到海量 MAC(疑似泛洪/环路)。定位该端口下挂什么,配 port-security 限制"
                                            "每端口 MAC 数止血,排查二层环路或异常主机;这是 MAC 表被打满的根因。"},
        {"id": "done_real_scale", "summary": "MAC 分布正常但总量接近上限=真实规模大。评估交换机 MAC 表容量,"
                                          "拆分广播域/VLAN 减少单表规模,或升级到表更大的设备。"},
     ]},
    {**_C,
     "id": "network.reachability.arp-incomplete", "name": "ARP 解析失败排查(网关/主机不通)",
     "taxonomy": "network/reachability/arp-incomplete",
     "symptom": "ping 不通同网段/ARP 表项 incomplete/解析不到对端 MAC/网关不通",
     "checks": [
        {"id": "check_incomplete", "title": "查 incomplete/未解析的 ARP 表项",
         "cmds": {"cisco_ios": "show ip arp | include Incomplete",
                  "huawei_vrp": "display arp | include Incomplete|I - "},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_intf"},
                      {"when": "output.value == 0", "goto": "done_arp_resolved"}],
         "otherwise": "check_intf",
         "cautions": ["ARP 表项 Incomplete=发了 ARP 请求但没收到应答,解析不到对端 MAC,二层就发不出去;"
                      "先分清是对端真不在/没响应,还是中间二层不通(VLAN 不对/端口 down/被隔离)"]},
        {"id": "check_intf", "title": "查相关接口是否 up",
         "cmds": {"cisco_ios": "show ip interface brief | include up",
                  "huawei_vrp": "display ip interface brief | include up"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_l2_issue"},
                      {"when": "output.value == 0", "goto": "done_intf_down"}],
         "otherwise": "escalate",
         "cautions": ["接口/SVI down 时该网段 ARP 必然解析不了;接口 up 却 incomplete 则问题在二层路径"
                      "(VLAN 不匹配、端口隔离、对端主机防火墙丢 ARP)"]},
     ],
     "dones": [
        {"id": "done_arp_resolved", "summary": "ARP 均已解析。不通另查(三层路由/ACL/对端服务/更高层)。"},
        {"id": "done_intf_down", "summary": "相关接口/SVI down 导致 ARP 解析失败。先恢复接口(物理链路/no shutdown/"
                                         "VLAN 接口状态);接口起来 ARP 才能正常解析。"},
        {"id": "done_l2_issue", "summary": "接口 up 但 ARP incomplete=二层路径不通。查 VLAN 是否两端一致、端口是否被隔离"
                                         "(port-isolate/PVLAN)、对端主机是否在线且未防火墙丢 ARP;必要时抓包看 ARP 请求是否到对端。"},
     ]},
    {**_C,
     "id": "network.physical.input-drops", "name": "接口输入丢包排查(收方向)",
     "taxonomy": "network/physical/input-drops",
     "symptom": "接口 input drops/收方向丢包/overrun/no buffer/收包丢但发正常",
     "checks": [
        {"id": "check_indrops", "title": "查接口输入丢包/溢出",
         "cmds": {"cisco_ios": "show interfaces | include input.*drops|overrun|no buffer|ignored",
                  "huawei_vrp": "display interface | include Input.*drop|Overrun|buffer"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_rate"},
                      {"when": "output.value == 0", "goto": "done_no_indrop"}],
         "otherwise": "check_rate",
         "cautions": ["输入丢包(input drops/overrun/no buffer)多在收方向缓冲不够或收包处理跟不上:CPU 忙、"
                      "中断处理慢、或瞬时收包超过接口/驱动缓冲——和输出丢包(拥塞)成因不同,别混为一谈"]},
        {"id": "check_rate", "title": "看输入速率是否接近接口能力",
         "cmds": {"cisco_ios": "show interfaces | include input rate|rxload",
                  "huawei_vrp": "display interface | include input rate|InUti"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_overrun"},
                      {"when": "output.value == 0", "goto": "done_buffer_tune"}],
         "otherwise": "escalate",
         "cautions": ["overrun(收方硬件来不及取走帧)常伴随高收包率或 CPU 繁忙;ignored/no buffer 多为缓冲资源不足。"
                      "持续 input drops 会造成上层重传、吞吐下降"]},
     ],
     "dones": [
        {"id": "done_no_indrop", "summary": "接口无输入丢包。收包问题另查(错包 CRC/双工/光功率/对端发送)。"},
        {"id": "done_overrun", "summary": "输入丢包伴高收包率=收方处理/缓冲跟不上。查设备 CPU 是否繁忙、是否有异常大流量"
                                       "(攻击/环路)冲击;分流或升级接口,必要时优化收包路径(硬件转发/中断)。"},
        {"id": "done_buffer_tune", "summary": "输入丢包但速率不高,多为缓冲资源不足或突发。调整接口收缓冲/队列、"
                                           "排查是否微突发冲击;若持续 ignored/no buffer 需查设备缓冲配置与整体负载。"},
     ]},
]
