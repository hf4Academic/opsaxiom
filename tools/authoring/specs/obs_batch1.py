"""H-6 obs 域批量 spec（第一批）——Prometheus/Alertmanager/Grafana 可观测性。"""

_O = {"capability_level": "read", "connector": "ssh", "facts": ["os.family"]}

SPECS = [
    {**_O,
     "id": "obs.metrics.prometheus-tsdb-full", "name": "Prometheus TSDB 撑盘排查",
     "taxonomy": "obs/metrics/prometheus-tsdb-full",
     "symptom": "Prometheus 磁盘满/TSDB 撑盘/查询变慢/OOM",
     "checks": [
        {"id": "check_series", "title": "查活跃时间序列数",
         "cmd": "curl -s 'localhost:9090/api/v1/status/tsdb' 2>/dev/null | grep -oE '\"numSeries\":[0-9]+' | grep -oE '[0-9]+'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 2000000", "goto": "check_cardinality"},
                      {"when": "output.value <= 2000000", "goto": "done_series_ok"}],
         "otherwise": "check_cardinality",
         "cautions": ["TSDB 大小主要由活跃 series 数决定，不是采集频率——series 爆炸(高基数标签)是撑盘首因"]},
        {"id": "check_cardinality", "title": "查高基数标签",
         "cmd": "curl -s 'localhost:9090/api/v1/status/tsdb' 2>/dev/null | grep -icE 'seriesCountByMetricName|labelValueCountByLabelName'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_cardinality"},
                      {"when": "output.value == 0", "goto": "done_retention"}],
         "otherwise": "escalate",
         "cautions": ["高基数标签(如把 request_id/user_id/pod_ip 当 label)会让 series 爆炸——"
                      "把这类高基数值放进 label 是 Prometheus 头号反模式"]},
     ],
     "dones": [
        {"id": "done_series_ok", "summary": "series 数不高。撑盘另查(retention 太长/采集目标太多)。"},
        {"id": "done_cardinality", "summary": "高基数标签导致 series 爆炸。定位问题 metric(status/tsdb 的 top10)，"
                                             "在 relabel 里 drop 高基数标签或该 metric；治本靠改埋点别把高基数值当 label。"},
        {"id": "done_retention", "summary": "series 不算爆炸，撑盘多为 retention 太长或目标太多。缩短 retention、"
                                           "或用远程存储(Thanos/VM)卸载历史数据。"},
     ]},
    {**_O,
     "id": "obs.metrics.scrape-timeout", "name": "Prometheus 抓取目标超时排查",
     "taxonomy": "obs/metrics/scrape-timeout",
     "symptom": "target 显示 down/scrape 超时/指标断点/context deadline exceeded",
     "checks": [
        {"id": "check_targets", "title": "查 down 的抓取目标数",
         "cmd": "curl -s 'localhost:9090/api/v1/targets' 2>/dev/null | grep -oE '\"health\":\"down\"' | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_duration"},
                      {"when": "output.value == 0", "goto": "done_all_up"}],
         "otherwise": "check_duration",
         "cautions": ["target down 分两类：连不上(网络/目标挂)vs 抓取超时(目标响应慢/指标太多)——"
                      "lastError 字段直接区分"]},
        {"id": "check_duration", "title": "看是否抓取耗时接近超时阈值",
         "cmd": "curl -s 'localhost:9090/api/v1/targets' 2>/dev/null | grep -icE 'context deadline exceeded|timeout'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_timeout"},
                      {"when": "output.value == 0", "goto": "done_unreachable"}],
         "otherwise": "escalate",
         "cautions": ["单个 target 暴露几万条指标会让 scrape 超时——大目标要么调大 scrape_timeout，"
                      "要么在目标侧减少指标"]},
     ],
     "dones": [
        {"id": "done_all_up", "summary": "所有目标健康。指标断点另查(Prometheus 自身重启/远程写堆积)。"},
        {"id": "done_timeout", "summary": "抓取超时。目标指标太多则调大 scrape_timeout(不超过 interval)或精简指标；"
                                         "目标响应慢则优化目标的 /metrics 端点。"},
        {"id": "done_unreachable", "summary": "目标连不上(非超时)。查网络可达性、目标进程是否存活、"
                                             "服务发现是否把已下线的实例还留在列表里。"},
     ]},
    {**_O,
     "id": "obs.alerting.silence-leak", "name": "告警静默泄漏排查(该响的没响)",
     "taxonomy": "obs/alerting/silence-leak",
     "symptom": "该告警的没告警/告警被静默了/silence 忘了删",
     "checks": [
        {"id": "check_silences", "title": "查生效中的静默规则数",
         "cmd": "curl -s 'localhost:9093/api/v2/silences' 2>/dev/null | grep -oE '\"state\":\"active\"' | wc -l",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_expiry"},
                      {"when": "output.value == 0", "goto": "done_no_silence"}],
         "otherwise": "check_expiry",
         "cautions": ["运维临时静默(如维护窗口)后忘了删，是'该响的没响'的头号原因——"
                      "静默应设明确过期时间而非永久"]},
        {"id": "check_expiry", "title": "看是否有长期/永久静默",
         "cmd": "curl -s 'localhost:9093/api/v2/silences' 2>/dev/null | grep -icE '\"endsAt\":\"(20[3-9][0-9]|2[1-9])'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_long_silence"},
                      {"when": "output.value == 0", "goto": "done_check_match"}],
         "otherwise": "escalate",
         "cautions": ["静默的 matcher 写太宽(如只匹配 severity=warning)会误伤大量本该告警的项——"
                      "看 matcher 覆盖范围是否超出预期"]},
     ],
     "dones": [
        {"id": "done_no_silence", "summary": "无生效静默。该告警的没响另查(告警规则/路由/接收器配置)。"},
        {"id": "done_long_silence", "summary": "存在长期/永久静默，可能是维护后忘删。核对每条静默的创建人与理由，"
                                             "过期的删除；建立静默审计习惯(设过期时间、定期清理)。"},
        {"id": "done_check_match", "summary": "有静默但非长期。检查其 matcher 是否写太宽误伤了本该告警的项，"
                                             "收窄 matcher 范围。"},
     ]},
    {**_O,
     "id": "obs.metrics.remote-write-backlog", "name": "Prometheus 远程写堆积排查",
     "taxonomy": "obs/metrics/remote-write-backlog",
     "symptom": "远程写堆积/远端存储收不到数据/remote write 队列满",
     "checks": [
        {"id": "check_pending", "title": "查远程写待发样本数",
         "cmd": "curl -s localhost:9090/metrics 2>/dev/null | awk '/prometheus_remote_storage_samples_pending/{print \"pending\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.pending > 10000", "goto": "check_failed"},
                      {"when": "output.pending <= 10000", "goto": "done_backlog_ok"}],
         "otherwise": "check_failed",
         "cautions": ["pending 高且涨=发送速度跟不上产生速度，队列会满并丢样本；远端慢或网络是常见因"]},
        {"id": "check_failed", "title": "查发送失败样本数",
         "cmd": "curl -s localhost:9090/metrics 2>/dev/null | awk '/remote_storage_samples_failed_total/{print \"failed\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.failed > 0", "goto": "done_remote_err"},
                      {"when": "output.failed == 0", "goto": "done_throughput"}],
         "otherwise": "escalate",
         "cautions": ["failed 增长=远端在拒绝(限流/鉴权/格式)；只是 pending 高但不 failed=纯吞吐不够"]},
     ],
     "dones": [
        {"id": "done_backlog_ok", "summary": "远程写无明显堆积。远端收不到另查(远端存储自身/网络分区)。"},
        {"id": "done_remote_err", "summary": "远程写有失败样本。查远端返回的错误(429 限流/401 鉴权/400 格式)，"
                                            "对症解决；调整 remote_write 的 queue_config 与远端容量匹配。"},
        {"id": "done_throughput", "summary": "只是吞吐不够(pending 高但不 failed)。调大 max_shards/max_samples_per_send"
                                           "提升并发，或降低采集量；确认到远端的网络带宽足够。"},
     ]},
]
