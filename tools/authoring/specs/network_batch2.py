"""H-3 network 域批量 spec（第二批）——用本批扩展的语法树前缀(eth-trunk/vrrp/dhcp/port-security)。"""

_C = {"network": True, "devices": ["cisco_ios", "huawei_vrp"],
      "connector": "netconf", "capability_level": "read"}

SPECS = [
    {**_C,
     "id": "network.switching.lacp-bond-degraded", "name": "链路聚合(LACP/Eth-Trunk)降级排查",
     "taxonomy": "network/switching/lacp-bond-degraded",
     "symptom": "聚合口带宽减半/成员链路没全up/LACP 协商失败",
     "checks": [
        {"id": "check_members", "title": "查聚合组成员状态",
         "cmds": {"cisco_ios": "show etherchannel summary | include Po|P)",
                  "huawei_vrp": "display eth-trunk | include Up|Down|Selected"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_down"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "check_down",
         "cautions": ["cisco 里成员口标志：P=bundled(在用)，独立字母如 s/w/D 都不在转发；"
                      "华为看 Selected/Unselected，Unselected 成员不承载流量"]},
        {"id": "check_down", "title": "看有无未加入聚合的成员",
         "cmds": {"cisco_ios": "show etherchannel summary | include down|s -|w -",
                  "huawei_vrp": "display eth-trunk | include Unselect|Down"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_member_down"},
                      {"when": "output.value == 0", "goto": "done_all_up"}],
         "otherwise": "escalate",
         "cautions": ["成员没加入聚合最常见两因：两端 LACP 模式不匹配(active/passive 都 passive)、"
                      "或成员口速率/双工不一致。别只看物理 up——LACP 没协商成也不承载流量"]},
     ],
     "dones": [
        {"id": "done_all_up", "summary": "聚合成员均在转发。带宽问题另有原因(哈希不均导致单成员打满)，"
                                         "看各成员流量分布是否均衡、哈希算法是否适配流量特征。"},
        {"id": "done_member_down", "summary": "有成员未加入聚合导致带宽降级。核对两端 LACP 模式(至少一端 active)、"
                                             "成员口速率双工一致、以及是否被 err-disabled；修复后成员会重新协商加入。"},
     ]},
    {**_C,
     "id": "network.routing.vrrp-flapping", "name": "VRRP 主备震荡排查",
     "taxonomy": "network/routing/vrrp-flapping",
     "symptom": "VRRP 主备频繁切换/网关时通时断/master 反复变",
     "checks": [
        {"id": "check_state", "title": "查 VRRP 组状态与优先级",
         "cmds": {"cisco_ios": "show vrrp brief",
                  "huawei_vrp": "display vrrp brief"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_flap"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "check_flap",
         "cautions": ["两端都显示自己是 Master=脑裂，多因 VRRP 通告收不到(链路/ACL 挡了组播 224.0.0.18)"]},
        {"id": "check_flap", "title": "查状态切换日志频率",
         "cmds": {"cisco_ios": "show logging | include VRRP|Master|Backup",
                  "huawei_vrp": "display logbuffer | include VRRP|MASTER|BACKUP"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 5", "goto": "done_flapping"},
                      {"when": "output.value <= 5", "goto": "done_stable"}],
         "otherwise": "escalate",
         "cautions": ["频繁切换常因：上行接口 track 抖动带动 VRRP 切、通告间隔/超时配置两端不一致、"
                      "或抢占(preempt)配置引起反复夺主。别忽视 track 的联动"]},
     ],
     "dones": [
        {"id": "done_stable", "summary": "VRRP 状态稳定。网关时断另查(ARP/上行/ACL)。"},
        {"id": "done_flapping", "summary": "VRRP 频繁切换。排查三处：①上行 track 对象是否抖动；"
                                          "②两端通告间隔与超时是否一致；③是否 preempt 配置引起反复夺主(可关抢占或调优先级差)。"},
     ]},
    {**_C,
     "id": "network.security-policy.dhcp-snooping-drop", "name": "DHCP 客户端拿不到地址排查(含 snooping)",
     "taxonomy": "network/security-policy/dhcp-snooping-drop",
     "symptom": "客户端拿不到 IP/DHCP 请求被丢/snooping 拦截",
     "checks": [
        {"id": "check_snoop", "title": "查 DHCP snooping 是否拦截",
         "cmds": {"cisco_ios": "show ip dhcp snooping | include drop|untrusted",
                  "huawei_vrp": "display dhcp snooping | include drop|discard"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_snoop_drop"},
                      {"when": "output.value == 0", "goto": "check_relay"}],
         "otherwise": "check_relay",
         "cautions": ["接 DHCP 服务器的上行口必须配成 trusted，否则 snooping 会把服务器的 OFFER 当"
                      "非法报文丢弃——这是启用 snooping 后最常见的'自己把自己坑了'"]},
        {"id": "check_relay", "title": "查 DHCP 中继配置",
         "cmds": {"cisco_ios": "show running-config | include ip helper-address",
                  "huawei_vrp": "display current-configuration | include dhcp relay"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_no_relay"},
                      {"when": "output.value > 0", "goto": "done_relay_ok"}],
         "otherwise": "escalate",
         "cautions": ["跨网段的 DHCP 必须配中继(helper-address 指向 DHCP 服务器)；同网段直连才不需要"]},
     ],
     "dones": [
        {"id": "done_snoop_drop", "summary": "DHCP snooping 在丢包。检查上行到 DHCP 服务器的端口是否配 trusted；"
                                            "非法源(私接的 DHCP 服务器)被拦是正常防护，定位并处理私接设备。"},
        {"id": "done_no_relay", "summary": "客户端与 DHCP 服务器跨网段但没配中继。在客户端网关接口配"
                                          " ip helper-address 指向 DHCP 服务器地址。"},
        {"id": "done_relay_ok", "summary": "中继已配，问题可能在 DHCP 服务器侧(地址池耗尽/作用域不对)"
                                          "或路径不通。到服务器查地址池，并确认中继与服务器间双向可达。"},
     ]},
    {**_C,
     "id": "network.security-policy.port-security-violation", "name": "端口安全违规排查",
     "taxonomy": "network/security-policy/port-security-violation",
     "symptom": "端口 port-security 违规/接入设备不通/学到超限 MAC",
     "checks": [
        {"id": "check_viol", "title": "查端口安全违规计数",
         "cmds": {"cisco_ios": "show port-security | include Violation|Shutdown|Secure",
                  "huawei_vrp": "display port-security | include violation|protect"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_mode"},
                      {"when": "output.value == 0", "goto": "done_no_viol"}],
         "otherwise": "check_mode",
         "cautions": ["违规动作三种：protect(丢包不告警)、restrict(丢包+告警)、shutdown(关端口)。"
                      "shutdown 模式下违规会让端口 err-disabled，接入设备彻底不通"]},
        {"id": "check_mode", "title": "看违规是否触发关端口",
         "cmds": {"cisco_ios": "show port-security | include Shutdown",
                  "huawei_vrp": "display port-security | include error-down|shutdown"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_shutdown"},
                      {"when": "output.value == 0", "goto": "done_dropping"}],
         "otherwise": "escalate",
         "cautions": ["MAC 数超限最常见于端口下接了小交换机/hub(多个 MAC)，或做了虚拟化(多 VM MAC)——"
                      "确认是否合法需求，是则调大 maximum，否则查私接"]},
     ],
     "dones": [
        {"id": "done_no_viol", "summary": "无端口安全违规。接入不通另查(VLAN/物理/认证)。"},
        {"id": "done_shutdown", "summary": "违规触发了端口关闭(err-disabled)。先确认超限 MAC 是否合法需求，"
                                          "合法则调大 maximum 或改违规动作为 restrict，再恢复端口；非法则查私接设备。"},
        {"id": "done_dropping", "summary": "违规在丢包(protect/restrict)但端口未关。同样先判 MAC 是否合法，"
                                          "调整 maximum 或清理私接；restrict 模式有告警可辅助定位。"},
     ]},
    {**_C,
     "id": "network.switching.trunk-vlan-mismatch", "name": "Trunk 允许 VLAN 不一致排查",
     "taxonomy": "network/switching/trunk-vlan-mismatch",
     "symptom": "跨交换机某 VLAN 不通/trunk 两端允许 VLAN 不一致/native vlan 不匹配",
     "checks": [
        {"id": "check_trunk", "title": "查 trunk 允许的 VLAN 列表",
         "cmds": {"cisco_ios": "show interfaces trunk",
                  "huawei_vrp": "display port vlan | include trunk|hybrid"},
         "parser": "generic/table-v1",
         "branches": [{"when": "output.row_count > 0", "goto": "check_native"},
                      {"when": "output.row_count == 0", "goto": "done_no_trunk"}],
         "otherwise": "check_native",
         "cautions": ["某 VLAN 不通先看它在不在 trunk 允许列表里——两端 allowed vlan 必须都放行该 VLAN，"
                      "少一端就断"]},
        {"id": "check_native", "title": "查 native vlan 是否两端一致",
         "cmds": {"cisco_ios": "show interfaces trunk | include native|Native",
                  "huawei_vrp": "display port vlan | include default"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_check_native"},
                      {"when": "output.value == 0", "goto": "done_allowed_list"}],
         "otherwise": "escalate",
         "cautions": ["native vlan 两端不一致会导致该 VLAN 流量错配且 CDP 会告警——这是 trunk 配置的经典坑"]},
     ],
     "dones": [
        {"id": "done_no_trunk", "summary": "该口不是 trunk(可能是 access)。跨交换机传多 VLAN 需配 trunk，"
                                          "确认拓扑与端口模式。"},
        {"id": "done_allowed_list", "summary": "核对 trunk 两端的 allowed vlan 列表——确保不通的那个 VLAN"
                                              "在两端都被放行；补齐缺失的一端。"},
        {"id": "done_check_native", "summary": "native vlan 相关。确认 trunk 两端 native vlan 一致，"
                                              "不一致会造成 VLAN 流量错配，改成两端相同。"},
     ]},
]
