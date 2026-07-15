"""H-5 middleware 域批量 spec（第二批）。"""

_M = {"capability_level": "read", "connector": "ssh"}

SPECS = [
    {**_M,
     "id": "middleware.kafka.consumer-lag", "name": "Kafka 消费积压排查",
     "taxonomy": "middleware/kafka/consumer-lag",
     "symptom": "Kafka 消费积压/lag 很大/消费跟不上生产",
     "params": {"group": "消费组名"},
     "checks": [
        {"id": "check_lag", "title": "查消费组总 lag",
         "cmd": "kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group {{group}} 2>/dev/null | awk 'NR>1{s+=$6} END{print s+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 10000", "goto": "check_state"},
                      {"when": "output.value <= 10000", "goto": "done_lag_ok"}],
         "otherwise": "check_state",
         "cautions": ["lag 大要看是持续增长还是稳定——稳定的固定 lag(如批处理)无害，持续涨才是消费跟不上"]},
        {"id": "check_state", "title": "查消费组状态是否稳定",
         "cmd": "kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group {{group}} --state 2>/dev/null | grep -ic 'Stable'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_slow_consumer"},
                      {"when": "output.value == 0", "goto": "done_rebalancing"}],
         "otherwise": "escalate",
         "cautions": ["消费并行度上限=分区数，消费者多于分区也没用；lag 大且组稳定=消费处理慢或分区不够"]},
     ],
     "dones": [
        {"id": "done_lag_ok", "summary": "lag 不大，消费正常。若业务觉得慢查端到端时延而非积压。"},
        {"id": "done_slow_consumer", "summary": "组稳定但 lag 涨=消费处理慢或分区不足。优化消费逻辑、"
                                               "加消费者实例(不超过分区数)、或增加分区数提升并行度。"},
        {"id": "done_rebalancing", "summary": "消费组不稳定(在 rebalance)。频繁 rebalance 会让消费停滞——"
                                             "查是否消费者频繁加入退出、max.poll.interval 超时被踢、心跳配置。"},
     ]},
    {**_M,
     "id": "middleware.mysql.slow-query-storm", "name": "MySQL 慢查询风暴排查",
     "taxonomy": "middleware/mysql/slow-query-storm",
     "symptom": "MySQL 突然变慢/慢查询暴增/CPU 高/连接堆积",
     "checks": [
        {"id": "check_running", "title": "查当前长时间运行的查询",
         "cmd": "mysql -e \"SELECT COUNT(*) c FROM information_schema.processlist WHERE command='Query' AND time>5\" 2>/dev/null | tail -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 5", "goto": "check_lock"},
                      {"when": "output.value <= 5", "goto": "done_few_slow"}],
         "otherwise": "check_lock",
         "cautions": ["同一条 SQL 大量并发慢=多为缺索引全表扫；先看是不是集中在某条语句(processlist 的 info)"]},
        {"id": "check_lock", "title": "看是否有锁等待放大",
         "cmd": "mysql -e \"SELECT COUNT(*) c FROM information_schema.processlist WHERE state LIKE '%lock%'\" 2>/dev/null | tail -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_lock_pileup"},
                      {"when": "output.value == 0", "goto": "done_missing_index"}],
         "otherwise": "escalate",
         "cautions": ["锁等待会让原本快的查询也排队变慢——一条持锁的大事务能拖垮全库；"
                      "别只优化慢 SQL 而忽略锁源"]},
     ],
     "dones": [
        {"id": "done_few_slow", "summary": "长查询不多。变慢另查(连接数/内存/磁盘 IO)。"},
        {"id": "done_lock_pileup", "summary": "锁等待放大了慢查询。定位持锁的大事务/长事务(information_schema"
                                            ".innodb_trx)，处理它(提交/回滚/优化)，排队的查询会随之疏通。"},
        {"id": "done_missing_index", "summary": "大量慢查询且无锁，多为缺索引全表扫或突发大查询。"
                                               "从 processlist 或慢日志抓 SQL，EXPLAIN 看执行计划补索引；限流大查询。"},
     ]},
    {**_M,
     "id": "middleware.es.disk-watermark", "name": "ES 磁盘水位锁写排查",
     "taxonomy": "middleware/es/disk-watermark",
     "symptom": "ES 无法写入/索引变只读/磁盘水位告警/read_only_allow_delete",
     "checks": [
        {"id": "check_ro", "title": "查是否有索引被置为只读",
         "cmd": "curl -s 'localhost:9200/_all/_settings' 2>/dev/null | grep -ic 'read_only_allow_delete.*true'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_disk"},
                      {"when": "output.value == 0", "goto": "done_not_ro"}],
         "otherwise": "check_disk",
         "cautions": ["ES 磁盘超 flood_stage(默认 95%)会自动给索引加 read_only_allow_delete 块——"
                      "清理磁盘后块不会自动解除，必须手动清除该设置"]},
        {"id": "check_disk", "title": "查节点磁盘使用",
         "cmd": "curl -s 'localhost:9200/_cat/allocation?h=disk.percent' 2>/dev/null | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 85", "goto": "done_disk_full"},
                      {"when": "output.value <= 85", "goto": "done_clear_block"}],
         "otherwise": "escalate",
         "cautions": ["三档水位：low(85%)停止分配新分片、high(90%)迁移分片走、flood(95%)锁写。"
                      "别只清磁盘忘了解锁"]},
     ],
     "dones": [
        {"id": "done_not_ro", "summary": "无只读索引。写入失败另查(mapping/线程池/集群健康)。"},
        {"id": "done_disk_full", "summary": "磁盘超水位导致锁写。先清理(删旧索引/扩盘)把磁盘降到 flood 以下，"
                                          "再手动解除只读块：PUT _all/_settings {read_only_allow_delete:null}。"},
        {"id": "done_clear_block", "summary": "磁盘已降下来但只读块残留(不会自动解)。手动清除："
                                             "PUT _all/_settings 把 read_only_allow_delete 设为 null，写入即恢复。"},
     ]},
    {**_M,
     "id": "middleware.nginx.worker-connections-full", "name": "Nginx worker 连接耗尽排查",
     "taxonomy": "middleware/nginx/worker-connections-full",
     "symptom": "Nginx worker_connections are not enough/新连接被拒/并发上不去",
     "checks": [
        {"id": "check_errlog", "title": "查是否报连接不足",
         "cmd": "tail -500 /var/log/nginx/error.log 2>/dev/null | grep -ic 'worker_connections are not enough'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_ulimit"},
                      {"when": "output.value == 0", "goto": "done_not_this"}],
         "otherwise": "check_ulimit",
         "cautions": ["worker 总连接上限 = worker_processes × worker_connections；反代场景每个客户端连接"
                      "还要占一个到上游的连接，实际容量要除以 2"]},
        {"id": "check_ulimit", "title": "查进程 fd 上限是否够",
         "cmd": "cat /proc/$(pgrep -o nginx)/limits 2>/dev/null | awk '/open files/{print \"nofile\", $4}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.nofile < 10240", "goto": "done_ulimit_low"},
                      {"when": "output.nofile >= 10240", "goto": "done_raise_conn"}],
         "otherwise": "escalate",
         "cautions": ["worker_connections 调再大，若进程 nofile(ulimit -n)不够也白搭——两者要一起调；"
                      "systemd 管理的 nginx 要改 LimitNOFILE"]},
     ],
     "dones": [
        {"id": "done_not_this", "summary": "非连接耗尽。并发上不去另查(上游慢/CPU/keepalive 配置)。"},
        {"id": "done_ulimit_low", "summary": "进程 fd 上限太低卡住了连接数。先调大 nginx 进程的 LimitNOFILE"
                                            "(systemd)或 worker_rlimit_nofile，再调 worker_connections。"},
        {"id": "done_raise_conn", "summary": "fd 够，需调大 worker_connections。评估内存后上调，"
                                            "反代场景记得容量要按需求×2；同时确认 worker_processes 匹配核数。"},
     ]},
    {**_M,
     "id": "middleware.rabbitmq.queue-backlog", "name": "RabbitMQ 队列堆积排查",
     "taxonomy": "middleware/rabbitmq/queue-backlog",
     "symptom": "RabbitMQ 队列消息堆积/消费不及时/内存告警",
     "checks": [
        {"id": "check_ready", "title": "查堆积最多的队列",
         "cmd": "rabbitmqctl list_queues name messages 2>/dev/null | sort -k2 -rn | head -3 | awk '{print $2}' | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 10000", "goto": "check_consumers"},
                      {"when": "output.value <= 10000", "goto": "done_backlog_ok"}],
         "otherwise": "check_consumers",
         "cautions": ["消息堆积会占内存，超过 vm_memory_high_watermark(默认 40%)会阻塞生产者(流控)——"
                      "堆积不处理最终会连生产一起卡"]},
        {"id": "check_consumers", "title": "看该队列有无消费者",
         "cmd": "rabbitmqctl list_queues name consumers 2>/dev/null | sort -k2 -n | head -1 | awk '{print $2}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_no_consumer"},
                      {"when": "output.value > 0", "goto": "done_slow_consumer"}],
         "otherwise": "escalate",
         "cautions": ["消费者数为 0=没人消费(消费者挂了/没连上)，堆积必然；有消费者仍堆=消费处理慢或"
                      "prefetch 太小限制了吞吐"]},
     ],
     "dones": [
        {"id": "done_backlog_ok", "summary": "队列堆积不严重。若有告警看是否某队列个别堆积或内存其它占用。"},
        {"id": "done_no_consumer", "summary": "堆积队列没有消费者。查消费者进程是否挂了/连接断了/绑定错队列；"
                                             "恢复消费者后积压会被消化。"},
        {"id": "done_slow_consumer", "summary": "有消费者但消费慢。优化消费逻辑、增加消费者、"
                                               "调大 prefetch_count 提升吞吐(权衡公平性)；确认没有 unacked 消息卡住。"},
     ]},
]
