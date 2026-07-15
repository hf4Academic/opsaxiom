"""H-push network 域批量 spec（第四批）——BGP前缀超限/非对称路由/ACL遮蔽/风暴抑制/微突发/双工。"""

_C = {"network": True, "devices": ["cisco_ios", "huawei_vrp"],
      "connector": "netconf", "capability_level": "read"}

SPECS = [
    {**_C,
     "id": "network.routing.bgp-max-prefix", "name": "BGP 前缀数超限排查",
     "taxonomy": "network/routing/bgp-max-prefix",
     "symptom": "BGP 邻居被断/max-prefix 触发/收到路由数超阈值/邻居 Idle(PfxCt)",
     "checks": [
        {"id": "check_log", "title": "查是否有 max-prefix 触发日志",
         "cmds": {"cisco_ios": "show logging | include MAXPFX|max-prefix|prefix limit",
                  "huawei_vrp": "display logbuffer | include maximum|prefix|EXCEED"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_peer"},
                      {"when": "output.value == 0", "goto": "done_no_maxpfx"}],
         "otherwise": "check_peer",
         "cautions": ["max-prefix 是保护机制:邻居发来的前缀数超过配置上限时,为防内存/表爆炸主动断开该邻居——"
                      "断的是'收太多'的那一侧,根因在对端为何突然通告海量前缀"]},
        {"id": "check_peer", "title": "查该邻居当前状态与前缀数",
         "cmds": {"cisco_ios": "show ip bgp summary | include Idle|Active",
                  "huawei_vrp": "display bgp peer | include Idle|Active"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_peer_down"},
                      {"when": "output.value == 0", "goto": "done_near_limit"}],
         "otherwise": "escalate",
         "cautions": ["被 max-prefix 断开的邻居常卡在 Idle,且很多实现不会自动恢复(需手动 clear 或配 restart)——"
                      "光调大上限没用,得先确认对端通告合理再恢复邻居"]},
     ],
     "dones": [
        {"id": "done_no_maxpfx", "summary": "无 max-prefix 触发。邻居异常另查(链路/认证/hold 超时/AS 配置)。"},
        {"id": "done_peer_down", "summary": "邻居因超限被断(Idle)。先核实对端为何通告海量前缀(误配/泄漏/去汇总),"
                                         "解决源头或用前缀过滤/汇总收敛;确认合理后调整上限并手动 clear 恢复邻居。"},
        {"id": "done_near_limit", "summary": "有触发迹象但邻居暂存活,可能接近上限。核对前缀数增长是否正常,"
                                          "配 max-prefix 的告警阈值(warning-only)提前预警,避免直接断邻居。"},
     ]},
    {**_C,
     "id": "network.reachability.asymmetric-routing", "name": "非对称路由排查(单向不通)",
     "taxonomy": "network/reachability/asymmetric-routing",
     "symptom": "单向能通反向不通/有防火墙时连接被丢/去回包走不同路径",
     "checks": [
        {"id": "check_route", "title": "查去往目的的路由路径",
         "cmds": {"cisco_ios": "show ip route | include via|Gateway",
                  "huawei_vrp": "display ip routing-table | include NextHop|Direct"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_multipath"},
                      {"when": "output.value == 0", "goto": "done_no_route"}],
         "otherwise": "check_multipath",
         "cautions": ["非对称路由本身在纯路由网络里合法(去回走不同路),问题出在有状态设备(防火墙/NAT)上——"
                      "它只看到单向流量,认为是非法连接而丢弃。先确认路径上有没有有状态设备"]},
        {"id": "check_multipath", "title": "看是否存在多条等价/冗余路径",
         "cmds": {"cisco_ios": "show ip route | include equal|ECMP|via",
                  "huawei_vrp": "display ip routing-table | include NextHop"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1", "goto": "done_asymmetric"},
                      {"when": "output.value <= 1", "goto": "done_single_path"}],
         "otherwise": "escalate",
         "cautions": ["多条路径/双出口是非对称的温床:去走 A 回走 B,途经的防火墙各看半程会 drop;"
                      "解法是让去回经同一有状态设备,或在防火墙间做会话同步"]},
     ],
     "dones": [
        {"id": "done_no_route", "summary": "没有到目的的路由。补/修路由(缺省路由/明细路由/重分发),先解决可达性再谈方向。"},
        {"id": "done_asymmetric", "summary": "存在多路径导致非对称,途经有状态设备(防火墙/NAT)只见单向而丢弃。"
                                          "让去回流量经同一设备(策略路由/调整 metric),或在冗余防火墙间开会话同步。"},
        {"id": "done_single_path", "summary": "单路径却单向不通,多为反向路由缺失或 uRPF/ACL 挡了回包。检查目的侧到源的"
                                           "回程路由、uRPF 检查、以及沿途 ACL 是否只放行了单向。"},
     ]},
    {**_C,
     "id": "network.security-policy.acl-shadowing", "name": "ACL 规则遮蔽排查",
     "taxonomy": "network/security-policy/acl-shadowing",
     "symptom": "ACL 规则不生效/放行或拒绝没起作用/后面的规则被前面挡住",
     "checks": [
        {"id": "check_hits", "title": "查各 ACL 表项命中计数",
         "cmds": {"cisco_ios": "show access-lists | include matches|permit|deny",
                  "huawei_vrp": "display acl all | include rule|match"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_zero_hit"},
                      {"when": "output.value == 0", "goto": "done_no_acl"}],
         "otherwise": "check_zero_hit",
         "cautions": ["ACL 按顺序自上而下匹配,命中即停;某条规则命中数一直为 0,很可能被上面更宽的规则遮蔽了"
                      "(shadowing)——看命中计数是发现遮蔽最直接的手段"]},
        {"id": "check_zero_hit", "title": "看是否有始终零命中的规则",
         "cmds": {"cisco_ios": "show access-lists | include 0 matches",
                  "huawei_vrp": "display acl all | include 0 times"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_shadowed"},
                      {"when": "output.value == 0", "goto": "done_order_ok"}],
         "otherwise": "escalate",
         "cautions": ["零命中未必都是遮蔽(也可能确实没这类流量),但配合业务预期看:本该生效却零命中的,"
                      "基本就是被前面规则吃掉了。调整顺序把更具体的规则前置"]},
     ],
     "dones": [
        {"id": "done_no_acl", "summary": "该处无 ACL 或无命中数据。规则不生效另查(是否应用到接口/方向对不对/VTY)。"},
        {"id": "done_shadowed", "summary": "存在零命中规则,疑似被前面更宽规则遮蔽。核对本应生效的规则,把更具体的"
                                        "(窄网段/特定端口)移到宽规则前面;遮蔽也可能导致'以为拒了实际放行'的安全隐患。"},
        {"id": "done_order_ok", "summary": "无异常零命中,顺序大体合理。若某规则仍不达预期,核对匹配条件(网段掩码/端口/"
                                        "协议)是否写对、以及 ACL 是否真的挂到了目标接口的正确方向。"},
     ]},
    {**_C,
     "id": "network.switching.storm-control-triggered", "name": "风暴抑制触发排查",
     "taxonomy": "network/switching/storm-control-triggered",
     "symptom": "接口被 storm-control 压制/流量被限/广播多播被丢/接口进 err-disable",
     "checks": [
        {"id": "check_sc", "title": "查风暴抑制是否触发",
         "cmds": {"cisco_ios": "show storm-control | include Forwarding|Blocking|Link",
                  "huawei_vrp": "display storm-control | include over|discard|block"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_type"},
                      {"when": "output.value == 0", "goto": "done_not_triggered"}],
         "otherwise": "check_type",
         "cautions": ["storm-control 触发说明某类报文(广播/多播/未知单播)超过了设定阈值被压制;"
                      "先确认是真风暴(环路/异常主机)还是阈值设太低误伤了正常的多播业务(如视频组播)"]},
        {"id": "check_type", "title": "看是哪类报文超阈值",
         "cmds": {"cisco_ios": "show interfaces counters broadcast | include broadcast|multicast",
                  "huawei_vrp": "display interface | include broadcast|multicast"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_real_storm"},
                      {"when": "output.value == 0", "goto": "done_threshold_low"}],
         "otherwise": "escalate",
         "cautions": ["广播/未知单播暴涨多为二层环路或主机异常(根因要查);而多播暴涨可能是正常组播业务,"
                      "此时是阈值配得太严,该调高阈值而非一味压制"]},
     ],
     "dones": [
        {"id": "done_not_triggered", "summary": "风暴抑制未触发。接口异常另查(err-disable 其它原因/物理/双工)。"},
        {"id": "done_real_storm", "summary": "广播/未知单播超阈值=疑似真风暴。查二层环路(STP 状态/新接入设备)或异常主机,"
                                          "根治环路/隔离异常源;storm-control 是止血,不能替代查根因。"},
        {"id": "done_threshold_low", "summary": "疑似阈值过严误伤正常业务(如组播视频)。核对该接口承载的多播业务量,"
                                             "适当调高对应报文类型的抑制阈值,或对组播单独放行,避免误压正常流量。"},
     ]},
    {**_C,
     "id": "network.traffic.microburst", "name": "微突发丢包排查",
     "taxonomy": "network/traffic/microburst",
     "symptom": "带宽没满却丢包/output drops 增长/偶发丢包但平均利用率不高",
     "checks": [
        {"id": "check_drops", "title": "查接口输出队列丢包",
         "cmds": {"cisco_ios": "show interfaces | include output drops|total output drops",
                  "huawei_vrp": "display interface | include Output.*drop|discard"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_util"},
                      {"when": "output.value == 0", "goto": "done_no_drop"}],
         "otherwise": "check_util",
         "cautions": ["output drops 增长但平均带宽不高=典型微突发:流量在毫秒级瞬时打满端口缓冲,"
                      "而秒级平均看不出来——别被'利用率不高'迷惑,看的是瞬时而非平均"]},
        {"id": "check_util", "title": "看平均利用率是否其实不高",
         "cmds": {"cisco_ios": "show interfaces | include rate|load",
                  "huawei_vrp": "display interface | include rate|Load"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_microburst"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["微突发的缓解手段有限:加大接口 buffer/队列深度、把突发大的流量做整形(shaping)平滑、"
                      "或升速端口;监控上要用高频采样(秒级以下)才抓得到"]},
     ],
     "dones": [
        {"id": "done_no_drop", "summary": "接口无输出丢包。偶发丢包另查(链路错包/对端/上层重传)。"},
        {"id": "done_microburst", "summary": "有输出丢包但平均利用率不高=微突发。缓解:加大端口缓冲/队列深度、对突发源"
                                          "做流量整形平滑峰值、或提升端口速率;用高频采样确认突发形态,别只看秒级平均。"},
     ]},
    {**_C,
     "id": "network.physical.duplex-mismatch", "name": "双工不匹配排查",
     "taxonomy": "network/physical/duplex-mismatch",
     "symptom": "接口大量 CRC/late collision/半双工/链路慢且错包多/一端全双工一端半双工",
     "checks": [
        {"id": "check_duplex", "title": "查接口是否协商成半双工",
         "cmds": {"cisco_ios": "show interfaces | include half-duplex|Half",
                  "huawei_vrp": "display interface | include Half|half"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_errors"},
                      {"when": "output.value == 0", "goto": "done_full_duplex"}],
         "otherwise": "check_errors",
         "cautions": ["现代链路正常都应全双工;出现半双工多因一端写死速率/双工、另一端自协商,协商结果降级为半双工——"
                      "双工不匹配是 late collision 和 CRC 的经典元凶"]},
        {"id": "check_errors", "title": "看是否伴随冲突/错包",
         "cmds": {"cisco_ios": "show interfaces | include late collision|CRC|runts",
                  "huawei_vrp": "display interface | include CRC|Collision|Runts"},
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_mismatch"},
                      {"when": "output.value == 0", "goto": "done_half_no_err"}],
         "otherwise": "escalate",
         "cautions": ["late collision(迟到冲突)几乎就是双工不匹配的确诊指标——全双工不该有冲突;"
                      "两端配置要一致:要么都自协商,要么都写死同样的速率/双工"]},
     ],
     "dones": [
        {"id": "done_full_duplex", "summary": "接口全双工。慢/错包另查(线缆/光功率/速率协商/对端)。"},
        {"id": "done_mismatch", "summary": "半双工且有 late collision/CRC=双工不匹配确诊。统一两端配置:都改自协商,"
                                        "或都写死相同速率/双工;修正后 late collision 应消失、吞吐恢复。"},
        {"id": "done_half_no_err", "summary": "协商成半双工但暂无明显错包。仍建议统一两端为全双工/自协商避免隐患;"
                                           "核对是否有一端被手工写死导致协商降级。"},
     ]},
]
