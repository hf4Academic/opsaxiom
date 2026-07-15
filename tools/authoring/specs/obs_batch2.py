"""H-6 obs 域批量 spec（第二批）——日志管道/exporter/Grafana/告警抖动/追踪。"""

_O = {"capability_level": "read", "connector": "ssh", "facts": ["os.family"]}

SPECS = [
    {**_O,
     "id": "obs.logging.pipeline-lag", "name": "日志管道延迟排查(日志入库慢)",
     "taxonomy": "obs/logging/pipeline-lag",
     "symptom": "日志入库慢/Kibana 查不到最新日志/日志滞后几分钟到几小时",
     "checks": [
        {"id": "check_backlog", "title": "查采集侧缓冲队列积压",
         "cmd": "curl -s localhost:9600/_node/stats/pipelines 2>/dev/null | grep -oE '\"events\":\\{[^}]*\"queue_push_duration_in_millis\":[0-9]+' | grep -oE '[0-9]+$' | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1000", "goto": "check_out"},
                      {"when": "output.value <= 1000", "goto": "done_no_backlog"}],
         "otherwise": "check_out",
         "cautions": ["日志滞后先分清堵在哪一段：采集(agent)→缓冲(队列/kafka)→处理(logstash)→入库(ES)——"
                      "队列 push 耗时高说明下游(处理/入库)吃不下，往下游查"]},
        {"id": "check_out", "title": "看下游入库是否被反压",
         "cmd": "curl -s 'localhost:9200/_cat/thread_pool/write?h=queue,rejected' 2>/dev/null | awk '{q+=$1; r+=$2} END{print \"rejected\", r+0}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.rejected > 0", "goto": "done_es_backpressure"},
                      {"when": "output.rejected == 0", "goto": "done_pipeline_slow"}],
         "otherwise": "escalate",
         "cautions": ["ES write 线程池有 rejected=入库端已过载在丢/退，是全链路反压的根——"
                      "光扩采集端没用，得先让入库跟得上(扩分片/减副本/加节点)"]},
     ],
     "dones": [
        {"id": "done_no_backlog", "summary": "采集缓冲无明显积压。日志滞后另查(agent 采集延迟/时间戳时区/索引刷新间隔)。"},
        {"id": "done_es_backpressure", "summary": "入库端(ES write 线程池)有拒绝=下游过载反压全链路。扩容/加分片、"
                                               "临时降副本数或 refresh_interval 提升写入吞吐；入库跟上后积压自然消化。"},
        {"id": "done_pipeline_slow", "summary": "队列积压但入库未拒绝，多为处理层(grok/解析)太重或并发不足。"
                                              "优化重的 filter、加处理 worker、或把复杂解析下沉到入库前预处理。"},
     ]},
    {**_O,
     "id": "obs.metrics.exporter-stale", "name": "Exporter 假活排查(进程在但指标不更新)",
     "taxonomy": "obs/metrics/exporter-stale",
     "symptom": "exporter 进程活着但指标停在旧值/时间戳不动/监控看着正常其实是僵值",
     "checks": [
        {"id": "check_fresh", "title": "查 exporter 自身抓取耗时是否异常",
         "cmd": "curl -s -o /dev/null -w '%{time_total}' localhost:9100/metrics 2>/dev/null | awk '{print \"sec\", $1*1000}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.sec > 3000", "goto": "check_scrape_err"},
                      {"when": "output.sec <= 3000", "goto": "check_scrape_err"}],
         "otherwise": "check_scrape_err",
         "cautions": ["exporter '假活'最坑：端口通、进程在、/metrics 有输出，但底层采集线程已挂或卡死，"
                      "指标定格在最后一次成功值——只看进程存活会漏判"]},
        {"id": "check_scrape_err", "title": "看是否有采集子系统报错",
         "cmd": "journalctl -u node_exporter --since '-10min' 2>/dev/null | grep -icE 'error|failed|timeout|collector.*failed'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_collector_fail"},
                      {"when": "output.value == 0", "goto": "done_maybe_stale"}],
         "otherwise": "escalate",
         "cautions": ["某个 collector 卡住(如坏盘让 diskstats 采集 hang)会拖住整个 exporter 抓取——"
                      "日志里 collector failed 直接点名是哪个子采集器出问题"]},
     ],
     "dones": [
        {"id": "done_collector_fail", "summary": "某采集子系统报错(如坏盘卡住 diskstats)。定位报错的 collector，"
                                              "修其底层问题(换盘/修权限)或临时禁用该 collector 让其余指标恢复更新。"},
        {"id": "done_maybe_stale", "summary": "无明显报错但疑似僵值。用 up 指标+时间戳新鲜度告警(而非只看进程)确认；"
                                            "重启 exporter 观察指标是否恢复跳动，并加'指标不更新'类活性告警防复发。"},
     ]},
    {**_O,
     "id": "obs.grafana.slow-dashboard", "name": "Grafana 面板加载慢排查",
     "taxonomy": "obs/grafana/slow-dashboard",
     "symptom": "Grafana 打开慢/面板转圈/查询超时/大盘卡顿",
     "checks": [
        {"id": "check_query_slow", "title": "查数据源查询慢日志",
         "cmd": "journalctl -u grafana-server --since '-15min' 2>/dev/null | grep -icE 'slow query|query took|context deadline|datasource.*timeout'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_range"},
                      {"when": "output.value == 0", "goto": "done_not_query"}],
         "otherwise": "check_range",
         "cautions": ["面板慢九成是背后查询慢，不是 Grafana 本身——先分清是查询慢还是渲染慢(太多 panel/序列)"]},
        {"id": "check_range", "title": "看是否大时间范围/高频刷新放大了查询",
         "cmd": "curl -s 'localhost:9090/api/v1/status/tsdb' 2>/dev/null | grep -oE '\"numSeries\":[0-9]+' | grep -oE '[0-9]+'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1000000", "goto": "done_heavy_query"},
                      {"when": "output.value <= 1000000", "goto": "done_dashboard_heavy"}],
         "otherwise": "escalate",
         "cautions": ["大时间范围(如 30 天原始点)×高基数=查询要扫海量点必然慢；"
                      "该用 recording rule 预聚合或缩短默认范围，别让大盘每次实时算"]},
     ],
     "dones": [
        {"id": "done_not_query", "summary": "无查询慢日志。面板慢另查(Grafana 自身资源/浏览器渲染/网络到数据源)。"},
        {"id": "done_heavy_query", "summary": "高基数×大范围让查询扫太多点。用 recording rule 预聚合常用指标、"
                                            "缩短面板默认时间范围、降低自动刷新频率；治本减少高基数指标。"},
        {"id": "done_dashboard_heavy", "summary": "序列不算爆炸但面板重，多为单页 panel 过多或每个 panel 查询过重。"
                                                "拆分大盘、合并相似 panel、给重查询加缓存。"},
     ]},
    {**_O,
     "id": "obs.alerting.flapping", "name": "告警抖动排查(反复触发恢复)",
     "taxonomy": "obs/alerting/flapping",
     "symptom": "同一告警反复触发又恢复/告警风暴/一晚上几十条同名告警",
     "checks": [
        {"id": "check_flap", "title": "查近期同名告警的触发次数",
         "cmd": "curl -s 'localhost:9093/api/v2/alerts/groups' 2>/dev/null | grep -oE '\"fingerprint\":\"[a-f0-9]+\"' | sort | uniq -c | sort -rn | head -1 | awk '{print \"count\", $1}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.count > 5", "goto": "check_for"},
                      {"when": "output.count <= 5", "goto": "done_not_flap"}],
         "otherwise": "check_for",
         "cautions": ["告警在阈值附近来回穿越是抖动主因；治本靠告警规则的 for(持续多久才触发)和"
                      "合理的 recover 迟滞，而不是靠人去静默"]},
        {"id": "check_for", "title": "看规则是否缺少 for 持续时间",
         "cmd": "curl -s 'localhost:9090/api/v1/rules' 2>/dev/null | grep -oE '\"duration\":[0-9]+' | grep -oE '[0-9]+$' | sort -n | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_no_for"},
                      {"when": "output.value > 0", "goto": "done_threshold_edge"}],
         "otherwise": "escalate",
         "cautions": ["for:0(或没写)的规则=指标瞬时越线立刻告警，毛刺就报——加 for 让它'持续 N 分钟才算'，"
                      "抖动大半能消掉"]},
     ],
     "dones": [
        {"id": "done_not_flap", "summary": "无明显同名告警抖动。告警多另查(确实批量故障/路由分组配置)。"},
        {"id": "done_no_for", "summary": "规则缺 for 持续时间，毛刺即报。给抖动规则加 for(如 5m)让它持续越线才触发；"
                                       "配合合理阈值迟滞，抖动可大幅收敛。"},
        {"id": "done_threshold_edge", "summary": "有 for 但仍抖，多为阈值恰在指标常态波动区间。拉开触发/恢复阈值"
                                               "(迟滞带)、或改用趋势/分位数类判据，避免在常态波动边缘反复穿越。"},
     ]},
    {**_O,
     "id": "obs.logging.disk-pressure", "name": "日志撑盘排查(日志占满磁盘)",
     "taxonomy": "obs/logging/disk-pressure",
     "symptom": "磁盘被日志占满/var 满/日志轮转失效/服务因写不了日志报错",
     "checks": [
        {"id": "check_logdir", "title": "查日志目录占用",
         "cmd": "df /var/log 2>/dev/null | awk 'NR==2{print \"pct\", $5+0}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.pct > 85", "goto": "check_rotate"},
                      {"when": "output.pct <= 85", "goto": "done_disk_ok"}],
         "otherwise": "check_rotate",
         "cautions": ["日志撑盘常见根因是轮转没生效(logrotate 没跑/配置漏了新日志)或进程持着已删文件——"
                      "df 显示满但 du 找不到，多半是删了没释放的句柄"]},
        {"id": "check_rotate", "title": "看是否有进程持着已删除的日志文件",
         "cmd": "lsof 2>/dev/null | grep -c '(deleted)'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_deleted_held"},
                      {"when": "output.value == 0", "goto": "done_rotate_fail"}],
         "otherwise": "escalate",
         "cautions": ["rm 删了日志但进程还开着句柄，空间不释放——必须让进程重开日志(reopen/重启)或用 truncate；"
                      "这是'删了日志磁盘却没降'的经典坑"]},
     ],
     "dones": [
        {"id": "done_disk_ok", "summary": "日志目录未撑盘。磁盘满另查(其它目录/大文件/inode 耗尽)。"},
        {"id": "done_deleted_held", "summary": "有进程持着已删日志文件不放空间。让持有者 reopen 日志(如 nginx -s reopen、"
                                            "systemctl reload)或重启该进程，空间即释放;根治靠 logrotate 用 copytruncate/postrotate reopen。"},
        {"id": "done_rotate_fail", "summary": "日志真占满且非删除句柄问题，多为轮转没生效。检查 logrotate 是否跑"
                                            "(cron/timer)、配置是否覆盖该日志、size/rotate 是否合理;先手动清理再修轮转。"},
     ]},
    {**_O,
     "id": "obs.tracing.sampling-gap", "name": "链路追踪采样丢失排查(trace 不完整)",
     "taxonomy": "obs/tracing/sampling-gap",
     "symptom": "trace 断链/只看到部分 span/追踪数据不完整/采样率异常",
     "checks": [
        {"id": "check_drop", "title": "查 collector 是否在丢 span",
         "cmd": "curl -s localhost:8888/metrics 2>/dev/null | awk '/otelcol_processor_dropped_spans|refused_spans/{s+=$2} END{print \"dropped\", s+0}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.dropped > 0", "goto": "check_queue"},
                      {"when": "output.dropped == 0", "goto": "done_no_drop"}],
         "otherwise": "check_queue",
         "cautions": ["trace 断链先分清是采样策略(本就按比例丢)还是异常丢弃(collector 过载/队列满 refuse)——"
                      "dropped/refused 指标是异常丢，采样丢不算错"]},
        {"id": "check_queue", "title": "看导出队列是否满",
         "cmd": "curl -s localhost:8888/metrics 2>/dev/null | awk '/otelcol_exporter_queue_size/{print \"qsize\", $2}' | head -1",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.qsize > 1000", "goto": "done_queue_full"},
                      {"when": "output.qsize <= 1000", "goto": "done_backend_reject"}],
         "otherwise": "escalate",
         "cautions": ["导出队列满=后端(Jaeger/Tempo)吃不下或网络慢，collector 只能丢新 span——"
                      "扩后端或调大队列/批量，别只怪采集端"]},
     ],
     "dones": [
        {"id": "done_no_drop", "summary": "collector 未异常丢 span。trace 不完整多为采样策略(按比例采)或跨服务"
                                        "trace 上下文没透传(缺 header 传播);查各服务是否统一注入/透传 traceparent。"},
        {"id": "done_queue_full", "summary": "导出队列满导致丢 span。扩容追踪后端(Jaeger/Tempo)、调大 exporter 队列与"
                                          "批量、或降低采样率减压;后端跟上后 span 不再被丢。"},
        {"id": "done_backend_reject", "summary": "队列不满但有丢弃,多为后端返回错误(限流/鉴权/格式)。查 collector 到"
                                               "后端的 exporter 报错日志,对症修复;确认后端容量与 collector 发送速率匹配。"},
     ]},
]
