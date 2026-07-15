"""H-4 k8s 域批量 spec（第二批）——kubectl 只读命令。"""

_K = {"k8s": True, "capability_level": "read", "facts": ["k8s.version"]}

SPECS = [
    {**_K,
     "id": "k8s.workload.image-pull-slow", "name": "镜像拉取慢/超时排查",
     "taxonomy": "k8s/workload/image-pull-slow",
     "symptom": "Pod 卡在 ContainerCreating/镜像拉取慢/拉取超时",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_events", "title": "查镜像拉取相关事件",
         "cmd": "kubectl -n {{ns}} get events --field-selector reason=Pulling,reason=Failed 2>/dev/null | grep -ic 'pull\\|timeout\\|toomanyrequests'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_ratelimit"},
                      {"when": "output.value == 0", "goto": "done_no_pull_event"}],
         "otherwise": "check_ratelimit",
         "cautions": ["ContainerCreating 卡住不一定是拉镜像——也可能是挂卷/CNI 分配 IP 慢，看 events 才能确认"]},
        {"id": "check_ratelimit", "title": "看是否触发仓库限流",
         "cmd": "kubectl -n {{ns}} get events 2>/dev/null | grep -ic 'toomanyrequests\\|rate limit\\|429'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_ratelimit"},
                      {"when": "output.value == 0", "goto": "done_slow_registry"}],
         "otherwise": "escalate",
         "cautions": ["Docker Hub 对匿名拉取限流(每 IP 每 6 小时若干次)，大集群共用出口 IP 极易撞——"
                      "上镜像加速器或私有仓库缓存是根治手段"]},
     ],
     "dones": [
        {"id": "done_no_pull_event", "summary": "无镜像拉取事件，卡住多在挂卷或 CNI。describe Pod 看 Events"
                                              "定位是 volume 挂载还是网络分配。"},
        {"id": "done_ratelimit", "summary": "触发了仓库限流(toomanyrequests)。配镜像加速器/私有仓库缓存、"
                                           "或给节点配置带认证的拉取凭证提高配额。"},
        {"id": "done_slow_registry", "summary": "拉取慢但未限流，多为仓库带宽/网络路径慢或镜像太大。"
                                              "考虑就近部署仓库、精简镜像层、预热常用镜像到节点。"},
     ]},
    {**_K,
     "id": "k8s.storage.pvc-terminating-stuck", "name": "PVC/PV 卡 Terminating 排查",
     "taxonomy": "k8s/storage/pvc-terminating-stuck",
     "symptom": "PVC 删不掉卡 Terminating/PV 一直 Released 不释放",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_pvc", "title": "查卡 Terminating 的 PVC",
         "cmd": "kubectl -n {{ns}} get pvc 2>/dev/null | grep -c Terminating",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_users"},
                      {"when": "output.value == 0", "goto": "done_no_stuck"}],
         "otherwise": "check_users",
         "cautions": ["PVC 卡 Terminating 几乎总是 finalizer 在等——kubernetes.io/pvc-protection 要求"
                      "没有 Pod 还在用它才放行"]},
        {"id": "check_users", "title": "看是否还有 Pod 在用该 PVC",
         "cmd": "kubectl -n {{ns}} get pods -o json 2>/dev/null | grep -ic 'persistentVolumeClaim'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_still_used"},
                      {"when": "output.value == 0", "goto": "done_finalizer"}],
         "otherwise": "escalate",
         "cautions": ["强删 finalizer(patch 掉)是最后手段——底层存储可能还没释放，可能导致数据/卷泄漏，"
                      "务必先确认真没人用"]},
     ],
     "dones": [
        {"id": "done_no_stuck", "summary": "无卡 Terminating 的 PVC。存储问题另查(绑定/容量/CSI)。"},
        {"id": "done_still_used", "summary": "PVC 仍被 Pod 引用——这就是删不掉的原因(pvc-protection finalizer)。"
                                            "先删/迁走引用它的 Pod，PVC 会自动完成删除。"},
        {"id": "done_finalizer", "summary": "无 Pod 引用但仍卡，多为 CSI 驱动侧未完成卸载或 finalizer 残留。"
                                           "查 CSI 控制器日志；确认底层卷已释放后，才可作为最后手段移除 finalizer。"},
     ]},
    {**_K,
     "id": "k8s.control-plane.apiserver-throttling", "name": "apiserver 限流(429)排查",
     "taxonomy": "k8s/control-plane/apiserver-throttling",
     "symptom": "kubectl 变慢/报 429 Too Many Requests/客户端被限流",
     "checks": [
        {"id": "check_flowcontrol", "title": "查 apiserver 优先级与公平队列",
         "cmd": "kubectl get --raw /debug/api_priority_and_fairness/dump_priority_levels 2>/dev/null | grep -ic 'rejected'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_who"},
                      {"when": "output.value == 0", "goto": "done_no_reject"}],
         "otherwise": "check_who",
         "cautions": ["1.20+ 用 APF(API Priority and Fairness)做限流，rejected 计数说明有请求被丢；"
                      "别再靠老的 --max-requests-inflight 判断"]},
        {"id": "check_who", "title": "看是否某控制器/客户端狂发请求",
         "cmd": "kubectl get events -A 2>/dev/null | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1000", "goto": "done_client_storm"},
                      {"when": "output.value <= 1000", "goto": "done_apf_tune"}],
         "otherwise": "escalate",
         "cautions": ["失控的 controller/operator(reconcile 死循环)或大量 list-watch 是 apiserver 压力主因；"
                      "先找狂发请求的源，而非一味调大 apiserver 配额"]},
     ],
     "dones": [
        {"id": "done_no_reject", "summary": "APF 无拒绝。kubectl 慢另查(网络/etcd/大对象 list)。"},
        {"id": "done_client_storm", "summary": "疑似某客户端/控制器请求风暴。用 apiserver 审计日志或"
                                              " APF 的 flow schema 定位高频来源，修复其请求行为(加缓存/降频/修死循环)。"},
        {"id": "done_apf_tune", "summary": "请求量不算极端但仍被限。可为关键工作负载调整 APF 的"
                                          " FlowSchema/PriorityLevelConfiguration 提高其配额，保障核心请求。"},
     ]},
        {**_K,
     "id": "k8s.workload.init-container-stuck", "name": "Init 容器卡住排查",
     "taxonomy": "k8s/workload/init-container-stuck",
     "symptom": "Pod 卡 Init:0/1/Init 容器不完成/主容器起不来",
     "params": {"ns": "命名空间", "pod": "Pod 名"},
     "checks": [
        {"id": "check_init_status", "title": "查 Init 容器状态",
         "cmd": "kubectl -n {{ns}} get pod {{pod}} -o jsonpath='{.status.initContainerStatuses[*].state}' 2>/dev/null | grep -ic 'waiting\\|running'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_logs"},
                      {"when": "output.value == 0", "goto": "done_init_done"}],
         "otherwise": "check_logs",
         "cautions": ["Init 容器串行执行，前一个不成功后面和主容器都不起——Init:0/2 表示卡在第 1 个"]},
        {"id": "check_logs", "title": "查卡住的 Init 容器日志",
         "cmd": "kubectl -n {{ns}} logs {{pod}} -c $(kubectl -n {{ns}} get pod {{pod}} -o jsonpath='{.spec.initContainers[0].name}') 2>/dev/null | grep -ic 'error\\|waiting\\|timeout\\|refused'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_init_blocked"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["Init 容器常做'等依赖就绪'(等 DB/等 Service)——依赖不来它就永远等；"
                      "看它在等什么，问题在被等的那个依赖"]},
     ],
     "dones": [
        {"id": "done_init_done", "summary": "Init 容器已完成，卡住在主容器。转查主容器(镜像/探针/资源)。"},
        {"id": "done_init_blocked", "summary": "Init 容器日志显示在等待/报错。定位它依赖什么(DB/Service/配置)，"
                                             "解决被等的依赖；或 Init 逻辑本身有 bug(连错地址/超时太短)。"},
     ]},
]
