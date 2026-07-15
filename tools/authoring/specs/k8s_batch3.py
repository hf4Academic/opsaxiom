"""H-push k8s 域批量 spec（第三批）——kubectl 只读命令。"""

_K = {"k8s": True, "capability_level": "read", "facts": ["k8s.version"]}

SPECS = [
    {**_K,
     "id": "k8s.workload.readiness-probe-failing", "name": "readiness 探针失败排查(流量不进)",
     "taxonomy": "k8s/workload/readiness-probe-failing",
     "symptom": "Pod Running 但 Ready 0/1/Service 不转发流量/endpoints 里没这个 Pod",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_notready", "title": "查有多少 Pod 卡在未 Ready",
         "cmd": "kubectl -n {{ns}} get pods --no-headers 2>/dev/null | awk '{split($2,a,\"/\"); if(a[1]<a[2] && $3==\"Running\") c++} END{print c+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_events"},
                      {"when": "output.value == 0", "goto": "done_all_ready"}],
         "otherwise": "check_events",
         "cautions": ["Running 但 Ready 0/1=容器起来了但 readiness 探针没过——Service 只把流量给 Ready 的 Pod,"
                      "所以'进程在却没流量'多半是 readiness 卡住,不是进程挂了"]},
        {"id": "check_events", "title": "看是否有 readiness 探针失败事件",
         "cmd": "kubectl -n {{ns}} get events --field-selector reason=Unhealthy 2>/dev/null | grep -ic 'Readiness probe failed'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_probe_fail"},
                      {"when": "output.value == 0", "goto": "done_ready_gate"}],
         "otherwise": "escalate",
         "cautions": ["readiness 探针失败常因:探针路径/端口配错、应用启动慢但 initialDelay 太短、"
                      "依赖(DB/下游)没就绪应用自报未 ready——看应用日志确认它为啥说自己没好"]},
     ],
     "dones": [
        {"id": "done_all_ready", "summary": "Pod 均 Ready。流量不进另查(Service selector/端口/kube-proxy/NetworkPolicy)。"},
        {"id": "done_probe_fail", "summary": "readiness 探针在失败。核对探针配置(路径/端口/协议)、initialDelaySeconds 是否够应用启动、"
                                          "应用是否因依赖未就绪自报未 ready;修正后 Pod 进入 Ready 才会被加入 endpoints。"},
        {"id": "done_ready_gate", "summary": "未 Ready 但无探针失败事件,可能是 readinessGates/自定义条件未满足或探针刚开始。"
                                          "describe Pod 看 Conditions 与 readinessGates,确认卡在哪个门槛。"},
     ]},
    {**_K,
     "id": "k8s.scheduling.node-not-ready", "name": "节点 NotReady 排查",
     "taxonomy": "k8s/scheduling/node-not-ready",
     "symptom": "节点 NotReady/kubelet 失联/该节点 Pod 被驱逐或卡 Terminating",
     "checks": [
        {"id": "check_notready", "title": "查 NotReady 节点数",
         "cmd": "kubectl get nodes --no-headers 2>/dev/null | grep -c NotReady",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_cond"},
                      {"when": "output.value == 0", "goto": "done_all_ready"}],
         "otherwise": "check_cond",
         "cautions": ["节点 NotReady 先分清是 kubelet 挂了(节点整体失联)还是节点压力(磁盘/内存/PID)触发的状况——"
                      "两者处置完全不同,看 node conditions 才能定位"]},
        {"id": "check_cond", "title": "查节点异常状况(压力类)",
         "cmd": "kubectl get nodes -o json 2>/dev/null | grep -icE '\"type\":\"(MemoryPressure|DiskPressure|PIDPressure)\",\"status\":\"True\"'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_pressure"},
                      {"when": "output.value == 0", "goto": "done_kubelet_lost"}],
         "otherwise": "escalate",
         "cautions": ["有 *Pressure=True 说明是资源压力(盘满/内存/PID 耗尽)导致 kubelet 上报异常;"
                      "无压力却 NotReady=多为 kubelet 进程/网络/容器运行时(containerd)问题"]},
     ],
     "dones": [
        {"id": "done_all_ready", "summary": "所有节点 Ready。若有 Pod 异常另查(调度/镜像/探针),非节点问题。"},
        {"id": "done_pressure", "summary": "节点资源压力(磁盘/内存/PID)触发 NotReady。登上节点清理压力源"
                                        "(清盘/查内存大户/降 PID),压力解除后节点自动恢复 Ready;根治要给节点留足余量。"},
        {"id": "done_kubelet_lost", "summary": "无资源压力但 NotReady,多为 kubelet/容器运行时/网络问题。登节点看"
                                            "kubelet 与 containerd 服务状态与日志、到 apiserver 的网络连通,重启对应服务。"},
     ]},
    {**_K,
     "id": "k8s.workload.liveness-restart-loop", "name": "liveness 探针误杀重启排查",
     "taxonomy": "k8s/workload/liveness-restart-loop",
     "symptom": "Pod 反复重启但应用日志看着正常/RESTARTS 持续涨/疑似被 liveness 误杀",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_restarts", "title": "查高重启次数的 Pod",
         "cmd": "kubectl -n {{ns}} get pods --no-headers 2>/dev/null | awk '{if($4+0>5) c++} END{print c+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_killed"},
                      {"when": "output.value == 0", "goto": "done_no_restart"}],
         "otherwise": "check_killed",
         "cautions": ["高重启要分清是崩溃(CrashLoop,应用自己退)还是被杀(liveness kill/OOMKill)——"
                      "看容器 lastState 的 reason;应用日志正常却反复重启,高度怀疑 liveness 误杀"]},
        {"id": "check_killed", "title": "看是否有 liveness 探针失败事件",
         "cmd": "kubectl -n {{ns}} get events --field-selector reason=Unhealthy 2>/dev/null | grep -ic 'Liveness probe failed'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_liveness_kill"},
                      {"when": "output.value == 0", "goto": "done_other_restart"}],
         "otherwise": "escalate",
         "cautions": ["liveness 探针超时会 kill 容器重启——若应用在 GC/加载/高负载时短暂不响应探针,就被反复误杀,"
                      "陷入'越重启越忙越被杀'的循环;调大 timeoutSeconds/failureThreshold 是常见解法"]},
     ],
     "dones": [
        {"id": "done_no_restart", "summary": "无高重启 Pod。稳定性另查(偶发重启/节点驱逐历史)。"},
        {"id": "done_liveness_kill", "summary": "liveness 探针在杀容器(误杀)。放宽探针(调大 timeoutSeconds/periodSeconds/"
                                             "failureThreshold)、给慢启动配 startupProbe、确认探针检的是'真死'而非'暂时忙';避免越杀越糟。"},
        {"id": "done_other_restart", "summary": "高重启但非 liveness 失败,查容器 lastState reason:OOMKilled(调内存)、"
                                             "Error(应用崩,看退出码与日志)、或节点驱逐。对症处理。"},
     ]},
    {**_K,
     "id": "k8s.networking.networkpolicy-block", "name": "NetworkPolicy 误封流量排查",
     "taxonomy": "k8s/networking/networkpolicy-block",
     "symptom": "Pod 间突然不通/加了 NetworkPolicy 后连不上/服务调用被拒",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_np", "title": "查该命名空间是否有 NetworkPolicy",
         "cmd": "kubectl -n {{ns}} get networkpolicy --no-headers 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_default_deny"},
                      {"when": "output.value == 0", "goto": "done_no_np"}],
         "otherwise": "check_default_deny",
         "cautions": ["NetworkPolicy 是'白名单'模型:一旦某 Pod 被任一 policy 选中,未明确放行的流量全被拒——"
                      "'加了策略就不通'几乎都是漏配了必要的 ingress/egress 放行"]},
        {"id": "check_default_deny", "title": "查是否存在 default-deny 策略",
         "cmd": "kubectl -n {{ns}} get networkpolicy -o json 2>/dev/null | grep -icE '\"podSelector\":\\{\\}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_default_deny"},
                      {"when": "output.value == 0", "goto": "done_specific_np"}],
         "otherwise": "escalate",
         "cautions": ["podSelector:{} 选中命名空间内所有 Pod=default-deny,极易误伤;引入它后必须为每类必要通信"
                      "(DNS、到 DB、健康检查)显式放行,尤其别忘了放行 kube-dns 的 UDP/TCP 53"]},
     ],
     "dones": [
        {"id": "done_no_np", "summary": "该命名空间无 NetworkPolicy。不通另查(Service/CNI/kube-proxy/目标 Pod 未 Ready)。"},
        {"id": "done_default_deny", "summary": "存在 default-deny(全选)策略。核对是否为受影响流量配了放行规则;"
                                            "常见漏项是 DNS(53)与到依赖服务的 egress。按需补 ingress/egress 白名单。"},
        {"id": "done_specific_np", "summary": "有针对性策略在生效。核对其 podSelector/namespaceSelector/端口是否覆盖了"
                                           "当前被拒的通信;用 label 精确匹配源与目标,补齐缺失的放行项。"},
     ]},
    {**_K,
     "id": "k8s.resource.quota-exceeded", "name": "ResourceQuota 超限排查",
     "taxonomy": "k8s/resource/quota-exceeded",
     "symptom": "创建 Pod 报 exceeded quota/命名空间建不了新资源/deployment 扩不上去",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_quota", "title": "查该命名空间是否设了配额",
         "cmd": "kubectl -n {{ns}} get resourcequota --no-headers 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_events"},
                      {"when": "output.value == 0", "goto": "done_no_quota"}],
         "otherwise": "check_events",
         "cautions": ["建不了资源先确认是不是撞了 ResourceQuota;有配额时,Pod 必须声明 requests/limits 否则"
                      "直接被拒(配额生效的命名空间强制要求资源声明)"]},
        {"id": "check_events", "title": "看是否有 exceeded quota 拒绝事件",
         "cmd": "kubectl -n {{ns}} get events 2>/dev/null | grep -ic 'exceeded quota\\|forbidden.*quota'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_quota_hit"},
                      {"when": "output.value == 0", "goto": "done_quota_ok"}],
         "otherwise": "escalate",
         "cautions": ["报错会写明超了哪一项(cpu/memory/pods/pvc 数);对症才有效——是真不够用要提配额,"
                      "还是有僵尸资源没回收占着额度"]},
     ],
     "dones": [
        {"id": "done_no_quota", "summary": "该命名空间无 ResourceQuota。建不了资源另查(RBAC 权限/准入控制器/节点资源)。"},
        {"id": "done_quota_hit", "summary": "撞了 ResourceQuota。看超的是哪一项:清理该命名空间的僵尸/闲置资源腾额度,"
                                         "或评估后由管理员上调配额;确认新建资源都声明了 requests/limits。"},
        {"id": "done_quota_ok", "summary": "有配额但近期无超限拒绝。用 kubectl describe quota 看各项已用/上限余量,"
                                        "若接近上限提前扩额或清理,避免临界时创建失败。"},
     ]},
    {**_K,
     "id": "k8s.storage.volume-multiattach", "name": "卷多挂冲突排查(RWO 卷被抢)",
     "taxonomy": "k8s/storage/volume-multiattach",
     "symptom": "Pod 卡 ContainerCreating 报 Multi-Attach/卷挂不上/迁移后旧节点还占着卷",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_multiattach", "title": "查是否有 Multi-Attach 错误事件",
         "cmd": "kubectl -n {{ns}} get events 2>/dev/null | grep -ic 'Multi-Attach\\|volume is already exclusively attached\\|already used by pod'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_terminating"},
                      {"when": "output.value == 0", "goto": "done_no_multiattach"}],
         "otherwise": "check_terminating",
         "cautions": ["RWO(ReadWriteOnce)卷同一时刻只能被一个节点挂载;滚动更新/故障转移时,新 Pod 在别的节点起、"
                      "旧 Pod 还没完全释放卷,就报 Multi-Attach——本质是'旧的没放手,新的抢不到'"]},
        {"id": "check_terminating", "title": "看是否有旧 Pod 卡 Terminating 占着卷",
         "cmd": "kubectl -n {{ns}} get pods --no-headers 2>/dev/null | grep -c Terminating",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_stuck_old_pod"},
                      {"when": "output.value == 0", "goto": "done_node_gone"}],
         "otherwise": "escalate",
         "cautions": ["旧 Pod 卡 Terminating(节点失联/优雅退出卡住)会一直占着 RWO 卷,新 Pod 永远挂不上;"
                      "强删旧 Pod 前要确认它真的没在写卷,否则可能损坏数据"]},
     ],
     "dones": [
        {"id": "done_no_multiattach", "summary": "无 Multi-Attach 错误。卷挂不上另查(CSI 驱动/StorageClass/PV 绑定/节点无插件)。"},
        {"id": "done_stuck_old_pod", "summary": "旧 Pod 卡 Terminating 占着 RWO 卷。先让它正常结束(查它为何卡:节点失联/"
                                             "finalizer/优雅退出超时);确认无写入后再强删,卷释放后新 Pod 即可挂载。RWO 场景避免同时多副本。"},
        {"id": "done_node_gone", "summary": "无卡住 Pod 但仍报多挂,多为原节点异常(NotReady/宕机)使卷未被干净卸载。"
                                         "确认原节点状态,必要时由 CSI/存储侧强制 detach;考虑用 RWX 卷或改部署策略避免争抢。"},
     ]},
]
