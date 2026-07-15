"""H-4 k8s 域批量 spec（第一批）——kubectl 只读命令(get/describe/logs/top)。"""

_K = {"k8s": True, "capability_level": "read", "facts": ["k8s.version"]}

SPECS = [
    {**_K,
     "id": "k8s.networking.coredns-failing", "name": "CoreDNS 解析失败/慢排查",
     "taxonomy": "k8s/networking/coredns-failing",
     "symptom": "集群内 DNS 解析失败/服务名解析不了/解析很慢",
     "checks": [
        {"id": "check_pods", "title": "查 CoreDNS Pod 是否正常",
         "cmd": "kubectl -n kube-system get pods -l k8s-app=kube-dns --no-headers | grep -vc Running",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_pod_down"},
                      {"when": "output.value == 0", "goto": "check_logs"}],
         "otherwise": "check_logs",
         "cautions": ["CoreDNS 默认 2 副本，全挂则整集群 DNS 瘫痪；只挂一个仍能服务但容量减半"]},
        {"id": "check_logs", "title": "查 CoreDNS 日志有无错误",
         "cmd": "kubectl -n kube-system logs -l k8s-app=kube-dns --tail=100 2>/dev/null | grep -ic 'SERVFAIL\\|error\\|timeout'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_upstream"},
                      {"when": "output.value == 0", "goto": "done_config_or_ndots"}],
         "otherwise": "escalate",
         "cautions": ["CoreDNS 转发到上游(节点 /etc/resolv.conf)——上游 DNS 挂了 CoreDNS 也跟着 SERVFAIL；"
                      "解析慢常因 ndots:5 让每次查询放大成多次(先试 svc.ns.svc.cluster.local 等后缀)"]},
     ],
     "dones": [
        {"id": "done_pod_down", "summary": "CoreDNS Pod 有异常。describe 看重启原因(OOM/配置错)；"
                                          "全挂优先恢复，检查 configmap coredns 是否被改坏。"},
        {"id": "done_upstream", "summary": "CoreDNS 日志有错误。多为上游 DNS(节点 resolv.conf 指向的)不可达"
                                          "或超时——在节点上验证上游 DNS，或调整 forward 配置。"},
        {"id": "done_config_or_ndots", "summary": "CoreDNS 本身无明显错误，解析慢多为 ndots:5 放大查询。"
                                                  "应用内用 FQDN(带末尾点)可跳过 search 域；或调 Pod 的 dnsConfig 减少 ndots。"},
     ]},
    {**_K,
     "id": "k8s.control-plane.etcd-nospace", "name": "etcd 空间告警排查",
     "taxonomy": "k8s/control-plane/etcd-nospace",
     "symptom": "etcd alarm NOSPACE/apiserver 报 mvcc 空间满/集群只读",
     "checks": [
        {"id": "check_health", "title": "查 etcd 健康(经 apiserver 侧信号)",
         "cmd": "kubectl get --raw /healthz/etcd 2>&1 | grep -ic 'ok'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "check_events"},
                      {"when": "output.value > 0", "goto": "done_etcd_ok"}],
         "otherwise": "check_events",
         "cautions": ["不用 exec 进 etcd 容器跑 etcdctl(写权限风险)——apiserver 的 /healthz/etcd 已能反映健康"]},
        {"id": "check_events", "title": "查 events 里的 NOSPACE 信号",
         "cmd": "kubectl get events -A 2>/dev/null | grep -ic 'NOSPACE\\|mvcc\\|database space exceeded'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_nospace"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["etcd 默认配额 2GB，满了触发 NOSPACE 告警且集群转只读——写不进任何资源"]},
     ],
     "dones": [
        {"id": "done_etcd_ok", "summary": "etcd 健康。集群异常另查(apiserver/controller/网络)。"},
        {"id": "done_nospace", "summary": "etcd 空间满(NOSPACE)。**处置需 etcd 侧操作(人工/运维执行)："
                                          "compact 历史版本 + defrag 碎片整理 + 解除 alarm；根治调大 --quota-backend-bytes"
                                          "并排查是谁在狂写(如大量 events/失控 controller)。** Agent 不代执行 etcd 维护。"},
     ]},
    {**_K,
     "id": "k8s.scheduling.node-pressure", "name": "节点资源压力排查(Disk/PID/Memory Pressure)",
     "taxonomy": "k8s/scheduling/node-pressure",
     "symptom": "节点 DiskPressure/PIDPressure/Pod 被驱逐/调度不上去",
     "checks": [
        {"id": "check_conditions", "title": "查节点是否有 Pressure 状态",
         "cmd": "kubectl get nodes -o json 2>/dev/null | grep -ic '\"type\": \"DiskPressure\".*\"status\": \"True\"\\|PIDPressure.*True\\|MemoryPressure.*True'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_which"},
                      {"when": "output.value == 0", "goto": "done_no_pressure"}],
         "otherwise": "check_which",
         "cautions": ["Pressure 状态会让 kubelet 主动驱逐 Pod 并给节点打不可调度污点——Pod 被 Evicted 常源于此"]},
        {"id": "check_which", "title": "看节点资源使用",
         "cmd": "kubectl top nodes --no-headers 2>/dev/null | awk '{print $3+0}' | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 85", "goto": "done_resource_high"},
                      {"when": "output.value <= 85", "goto": "done_disk_or_pid"}],
         "otherwise": "escalate",
         "cautions": ["top nodes 需 metrics-server；DiskPressure 看的是节点磁盘不是 CPU/内存——"
                      "磁盘压力常因镜像/日志/emptyDir 占满 kubelet 目录(/var/lib/kubelet)"]},
     ],
     "dones": [
        {"id": "done_no_pressure", "summary": "节点无 Pressure。调度失败/驱逐另查(污点容忍/亲和/配额)。"},
        {"id": "done_resource_high", "summary": "节点 CPU/内存使用高触发压力。定位高占用 Pod(top pods)，"
                                               "确认 requests/limits 是否合理；扩容节点或迁移负载。"},
        {"id": "done_disk_or_pid", "summary": "非 CPU/内存主导，多为 DiskPressure 或 PIDPressure。"
                                             "DiskPressure 清理节点镜像(crictl rmi)/日志；PIDPressure 查是否有 Pod 狂 fork。"},
     ]},
    {**_K,
     "id": "k8s.networking.ingress-5xx", "name": "Ingress 502/504 排查",
     "taxonomy": "k8s/networking/ingress-5xx",
     "symptom": "通过 Ingress 访问报 502/504/后端连不上",
     "params": {"ns": "命名空间", "svc": "后端 Service 名"},
     "checks": [
        {"id": "check_endpoints", "title": "查后端 Service 是否有就绪 Endpoints",
         "cmd": "kubectl -n {{ns}} get endpoints {{svc}} -o json 2>/dev/null | grep -ic '\"ip\":'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_no_endpoints"},
                      {"when": "output.value > 0", "goto": "check_ing_log"}],
         "otherwise": "check_ing_log",
         "cautions": ["502/504 第一嫌疑永远是后端没有就绪 Endpoint——Service 选不到 Pod 或 Pod 没 Ready，"
                      "Ingress 就无处转发"]},
        {"id": "check_ing_log", "title": "查 Ingress Controller 日志",
         "cmd": "kubectl -n ingress-nginx logs -l app.kubernetes.io/name=ingress-nginx --tail=100 2>/dev/null | grep -ic '502\\|504\\|upstream timed out'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_timeout"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["504=upstream 超时(后端处理慢或没响应)；502=后端返回非法响应或连接被拒。"
                      "两者根因不同，别混为一谈"]},
     ],
     "dones": [
        {"id": "done_no_endpoints", "summary": "后端 Service 无就绪 Endpoints。查 ①Service 的 selector 是否"
                                              "匹配到 Pod；②Pod 是否 Ready(readiness 探针)；③目标端口是否对。"},
        {"id": "done_timeout", "summary": "Ingress 日志有 5xx。504 看后端响应慢(扩容/优化后端、调大 proxy 超时)；"
                                         "502 看后端是否返回了非法响应或连接被拒(后端端口/协议不匹配)。"},
     ]},
    {**_K,
     "id": "k8s.workload.cronjob-not-running", "name": "CronJob 不触发排查",
     "taxonomy": "k8s/workload/cronjob-not-running",
     "symptom": "CronJob 到点不跑/没生成 Job/定时任务不执行",
     "params": {"ns": "命名空间", "name": "CronJob 名"},
     "checks": [
        {"id": "check_suspend", "title": "查 CronJob 是否被暂停",
         "cmd": "kubectl -n {{ns}} get cronjob {{name}} -o jsonpath='{.spec.suspend}' 2>/dev/null | grep -ic true",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_suspended"},
                      {"when": "output.value == 0", "goto": "check_last"}],
         "otherwise": "check_last",
         "cautions": ["suspend:true 会让 CronJob 完全不触发——排查第一步就看这个，最常见的'低级'原因"]},
        {"id": "check_last", "title": "查最近调度与失败历史",
         "cmd": "kubectl -n {{ns}} get jobs 2>/dev/null | grep -c {{name}}",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_never_scheduled"},
                      {"when": "output.value > 0", "goto": "done_ran_check_job"}],
         "otherwise": "escalate",
         "cautions": ["controller 时钟偏差 >100s 或 startingDeadlineSeconds 太小会让调度被跳过；"
                      "concurrencyPolicy:Forbid 且上次没跑完也会跳过本次"]},
     ],
     "dones": [
        {"id": "done_suspended", "summary": "CronJob 被 suspend。设 spec.suspend=false 恢复。"},
        {"id": "done_never_scheduled", "summary": "从未生成过 Job。核对 ①schedule 表达式(cron 5 段)是否正确；"
                                                 "②startingDeadlineSeconds 是否过小导致错过就跳过；③控制器时钟。"},
        {"id": "done_ran_check_job", "summary": "有生成 Job 但你觉得没跑，问题在 Job/Pod 层。describe 最近的 Job"
                                              "看是否失败(镜像/资源/命令)，看 Pod 日志定位。"},
     ]},
]
