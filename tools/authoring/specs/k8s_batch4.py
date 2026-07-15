"""H-push k8s 域批量 spec（第四批）——kubectl 只读命令。"""

_K = {"k8s": True, "capability_level": "read", "facts": ["k8s.version"]}

SPECS = [
    {**_K,
     "id": "k8s.workload.configmap-not-applied", "name": "ConfigMap/Secret 更新未生效排查",
     "taxonomy": "k8s/workload/configmap-not-applied",
     "symptom": "改了 ConfigMap 但 Pod 没用新值/配置更新不生效/环境变量还是旧的",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_mount_type", "title": "查 Pod 是以 env 还是 volume 方式用配置",
         "cmd": "kubectl -n {{ns}} get pods -o json 2>/dev/null | grep -icE 'configMapKeyRef|secretKeyRef'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_restart"},
                      {"when": "output.value == 0", "goto": "done_volume_mount"}],
         "otherwise": "check_restart",
         "cautions": ["ConfigMap 以环境变量(envFrom/valueFrom)注入的,改了 ConfigMap 不会自动更新——环境变量在容器"
                      "启动时就定死了,必须重建 Pod 才生效;以 volume 挂载的才会自动同步(有延迟)"]},
        {"id": "check_restart", "title": "看 Pod 是否在配置变更后重建过",
         "cmd": "kubectl -n {{ns}} get pods --no-headers 2>/dev/null | awk '{print $5}' | grep -icE '^[0-9]+d|[0-9]+h'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_need_rollout"},
                      {"when": "output.value == 0", "goto": "done_recently_restarted"}],
         "otherwise": "escalate",
         "cautions": ["env 方式的配置更新必须滚动重启工作负载(kubectl rollout restart)才生效;"
                      "很多人改完 ConfigMap 就等,结果 Pod 一直用旧值——它不会自己重启"]},
     ],
     "dones": [
        {"id": "done_volume_mount", "summary": "配置以 volume 挂载,会自动同步但有延迟(kubelet 同步周期,约分钟级)。"
                                            "稍等或确认 subPath 挂载(subPath 不会自动更新);仍不生效再查应用是否热加载配置文件。"},
        {"id": "done_need_rollout", "summary": "配置以 env 注入且 Pod 未重建=还在用旧值。执行 kubectl rollout restart"
                                            "触发滚动重启让新配置生效;这是 env 方式配置更新的必备步骤。"},
        {"id": "done_recently_restarted", "summary": "Pod 较新(疑似已重建)但仍不生效。核对 ConfigMap 是否真的更新了、"
                                                  "工作负载引用的 ConfigMap 名/key 是否正确、应用是否缓存了配置。"},
     ]},
    {**_K,
     "id": "k8s.scheduling.taint-blocking", "name": "污点阻塞调度排查",
     "taxonomy": "k8s/scheduling/taint-blocking",
     "symptom": "Pod 一直 Pending/有节点却调度不上/node had taints that pod didn't tolerate",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_events", "title": "查是否因污点无法调度",
         "cmd": "kubectl -n {{ns}} get events --field-selector reason=FailedScheduling 2>/dev/null | grep -ic 'taint'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_taints"},
                      {"when": "output.value == 0", "goto": "done_not_taint"}],
         "otherwise": "check_taints",
         "cautions": ["'had taints that the pod didn't tolerate'=节点有污点而 Pod 没配对应容忍;先分清是"
                      "该节点本就该被保护(如 master/专用节点)还是污点是意外残留(如节点异常自动打的污点没清)"]},
        {"id": "check_taints", "title": "查集群里带污点的节点数",
         "cmd": "kubectl get nodes -o json 2>/dev/null | grep -icE '\"effect\":\"(NoSchedule|NoExecute)\"'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_taint_found"},
                      {"when": "output.value == 0", "goto": "done_no_taint_now"}],
         "otherwise": "escalate",
         "cautions": ["节点异常(NotReady/压力)时,K8s 会自动打 NoExecute 污点驱逐 Pod;这类污点是'症状'——"
                      "该去修节点,而不是给 Pod 加容忍硬塞上去"]},
     ],
     "dones": [
        {"id": "done_not_taint", "summary": "非污点导致的调度失败。查其它原因(资源不足/亲和/节点选择器/PVC 拓扑)。"},
        {"id": "done_taint_found", "summary": "节点污点阻止了调度。区分处理:若该 Pod 确实应上这类节点,加对应 toleration;"
                                           "若污点是节点异常自动打的,去修节点(而非加容忍);若污点是误配,kubectl taint 移除。"},
        {"id": "done_no_taint_now", "summary": "有污点调度事件但当前查不到污点,可能污点已被清或节点已恢复。"
                                            "重新观察 Pod 是否已调度;若仍 Pending 转查资源/亲和等其它调度约束。"},
     ]},
    {**_K,
     "id": "k8s.networking.service-external-unreachable", "name": "Service 外部访问不通排查",
     "taxonomy": "k8s/networking/service-external-unreachable",
     "symptom": "NodePort/LoadBalancer 外部访问超时/集群内通外部不通/EXTERNAL-IP pending",
     "params": {"ns": "命名空间", "svc": "Service 名"},
     "checks": [
        {"id": "check_type", "title": "查 Service 类型与外部 IP 状态",
         "cmd": "kubectl -n {{ns}} get svc {{svc}} -o wide 2>/dev/null | grep -ic 'pending'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_lb_pending"},
                      {"when": "output.value == 0", "goto": "check_endpoints"}],
         "otherwise": "check_endpoints",
         "cautions": ["LoadBalancer 的 EXTERNAL-IP 卡 <pending>=云厂商 LB 没配好或缺 cloud-controller-manager"
                      "(自建集群没有 LB 实现);先分清是 LB 分配问题还是后端/网络问题"]},
        {"id": "check_endpoints", "title": "查 Service 是否有健康后端",
         "cmd": "kubectl -n {{ns}} get endpoints {{svc}} -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | wc -w",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_check_firewall"},
                      {"when": "output.value == 0", "goto": "done_no_endpoints"}],
         "otherwise": "escalate",
         "cautions": ["Service 没有 endpoints(后端为空),外部访问必然不通;多因 selector 不匹配或后端 Pod 未 Ready——"
                      "先确认有健康后端,再谈外部网络"]},
     ],
     "dones": [
        {"id": "done_lb_pending", "summary": "LoadBalancer 外部 IP 卡 pending。自建集群需装 LB 实现(MetalLB 等)或改用 NodePort/"
                                          "Ingress;云上则查 cloud-controller-manager、LB 配额与子网/安全组配置。"},
        {"id": "done_no_endpoints", "summary": "Service 无健康后端。核对 selector 与 Pod label 是否匹配、后端 Pod 是否 Ready"
                                            "(见 readiness 探针);后端补齐后外部才可能访问到。"},
        {"id": "done_check_firewall", "summary": "有后端但外部不通,问题在网络路径。查 NodePort 端口是否被云安全组/防火墙放行、"
                                              "externalTrafficPolicy 设置、kube-proxy 规则、以及节点到 Pod 的转发。"},
     ]},
    {**_K,
     "id": "k8s.storage.pvc-resize-stuck", "name": "PVC 在线扩容卡住排查",
     "taxonomy": "k8s/storage/pvc-resize-stuck",
     "symptom": "扩了 PVC 容量但没生效/FileSystemResizePending/Pod 里看不到扩容后的空间",
     "params": {"ns": "命名空间"},
     "checks": [
        {"id": "check_condition", "title": "查是否卡在文件系统扩容待处理",
         "cmd": "kubectl -n {{ns}} get pvc -o json 2>/dev/null | grep -icE 'FileSystemResizePending|Resizing'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_sc"},
                      {"when": "output.value == 0", "goto": "done_no_resize"}],
         "otherwise": "check_sc",
         "cautions": ["PVC 扩容分两步:底层卷扩容(存储侧)+文件系统扩容(节点侧);FileSystemResizePending 表示卷已扩,"
                      "但文件系统还没扩——很多驱动需要 Pod 重启或重新挂载才触发文件系统扩容"]},
        {"id": "check_sc", "title": "查 StorageClass 是否允许扩容",
         "cmd": "kubectl get storageclass -o json 2>/dev/null | grep -ic 'allowVolumeExpansion.*true'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_restart_pod"},
                      {"when": "output.value == 0", "goto": "done_expansion_disabled"}],
         "otherwise": "escalate",
         "cautions": ["StorageClass 必须 allowVolumeExpansion: true 才支持扩容;为 false 时改 PVC 大小根本不会触发扩容,"
                      "且这个开关不能事后随便改现有 PVC——需确认驱动支持"]},
     ],
     "dones": [
        {"id": "done_no_resize", "summary": "PVC 无扩容待处理状态。看不到新空间另查(是否真改了 PVC size、应用是否缓存了旧容量)。"},
        {"id": "done_restart_pod", "summary": "卷已扩但文件系统扩容待处理(SC 支持扩容)。多数 CSI 需重启用该 PVC 的 Pod"
                                           "触发文件系统在线/离线扩容;重启后 Pod 内应看到新容量。"},
        {"id": "done_expansion_disabled", "summary": "StorageClass 未开启 allowVolumeExpansion,无法扩容。确认底层驱动支持后"
                                                  "由管理员开启该选项(对新 PVC 生效);现有卷可能需迁移到支持扩容的 SC。"},
     ]},
    {**_K,
     "id": "k8s.control-plane.cert-expiry", "name": "集群证书临期排查",
     "taxonomy": "k8s/control-plane/cert-expiry",
     "symptom": "kubelet/apiserver 证书快过期/节点 NotReady 报证书错误/x509 certificate has expired",
     "checks": [
        {"id": "check_kubeadm", "title": "查控制面证书剩余有效期",
         "cmd": "kubeadm certs check-expiration 2>/dev/null | grep -icE '<invalid>|expired| [0-9]d '",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_kubelet"},
                      {"when": "output.value == 0", "goto": "done_certs_ok"}],
         "otherwise": "check_kubelet",
         "cautions": ["kubeadm 集群的控制面证书默认 1 年有效期,到期 apiserver/controller 之间通信失败,集群瘫痪——"
                      "这是'集群用了快一年突然崩'的经典原因,必须提前轮换"]},
        {"id": "check_kubelet", "title": "查节点是否报证书相关错误",
         "cmd": "kubectl get nodes -o json 2>/dev/null | grep -icE 'x509|certificate has expired|unable to verify'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_kubelet_cert"},
                      {"when": "output.value == 0", "goto": "done_cp_cert_expiring"}],
         "otherwise": "escalate",
         "cautions": ["kubelet 证书通常能自动轮换(rotateCertificates),但若轮换没开或 CA 出问题会到期;"
                      "节点 NotReady 且报 x509 就要查 kubelet 证书,别只盯着网络"]},
     ],
     "dones": [
        {"id": "done_certs_ok", "summary": "控制面证书有效期充足。仍有异常另查(网络/etcd/具体组件);建议纳入证书到期巡检提前预警。"},
        {"id": "done_kubelet_cert", "summary": "节点报证书错误(疑似 kubelet 证书过期)。确认 kubelet 证书自动轮换是否开启,"
                                            "手动为节点重新签发/审批 CSR;修复后节点恢复与 apiserver 通信。"},
        {"id": "done_cp_cert_expiring", "summary": "控制面证书临期(高优先)。用 kubeadm certs renew all 轮换控制面证书并重启"
                                                "相关静态 Pod;同步更新 kubeconfig;规划到期前的自动化轮换避免复发。"},
     ]},
]
