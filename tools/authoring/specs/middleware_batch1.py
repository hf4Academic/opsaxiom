"""H-5 middleware 域批量 spec（第一批）——redis/kafka/es/nginx，linux 平台命令。"""

_M = {"capability_level": "read", "connector": "ssh"}

SPECS = [
    {**_M,
     "id": "middleware.redis.aof-rewrite-storm", "name": "Redis AOF 重写风暴/fork 延迟排查",
     "taxonomy": "middleware/redis/aof-rewrite-storm",
     "symptom": "Redis 周期性卡顿/AOF 重写时延迟尖刺/fork 慢",
     "checks": [
        {"id": "check_fork", "title": "查最近一次 fork 耗时",
         "cmd": "redis-cli info stats 2>/dev/null | awk -F: '/latest_fork_usec/{print \"fork_usec\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.fork_usec > 100000", "goto": "check_mem"},
                      {"when": "output.fork_usec <= 100000", "goto": "done_fork_ok"}],
         "otherwise": "check_mem",
         "cautions": ["fork 耗时随内存增大而增大(要复制页表)——大实例(几十 GB)fork 就可能几百毫秒，"
                      "期间 Redis 阻塞。这是 AOF/RDB 重写卡顿的物理根因"]},
        {"id": "check_mem", "title": "查实例内存规模与 THP",
         "cmd": "redis-cli info memory 2>/dev/null | awk -F: '/used_memory:/{print \"used\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.used > 10000000000", "goto": "done_large_instance"},
                      {"when": "output.used <= 10000000000", "goto": "done_thp_suspect"}],
         "otherwise": "escalate",
         "cautions": ["THP=always 会让 fork 后的写时复制放大(2M 大页粒度)，Redis 官方明确建议关 THP；"
                      "另外 fork 期间的延迟尖刺常被误判为'网络问题'"]},
     ],
     "dones": [
        {"id": "done_fork_ok", "summary": "fork 耗时不高。周期性卡顿另查(慢命令/大 key/网络)。"},
        {"id": "done_large_instance", "summary": "大实例 fork 慢是物理必然。缓解：拆分实例减小单实例内存、"
                                                 "AOF 改用 everysec 且错峰重写、关 THP；根治靠减小单实例规模。"},
        {"id": "done_thp_suspect", "summary": "实例不算大但 fork 慢，重点查 THP 是否 always(关闭它)、"
                                             "宿主是否内存紧张导致 fork 时缺页慢。"},
     ]},
    {**_M,
     "id": "middleware.kafka.isr-shrink", "name": "Kafka ISR 收缩/副本不同步排查",
     "taxonomy": "middleware/kafka/isr-shrink",
     "symptom": "Kafka 分区 ISR 收缩/副本掉出同步/under-replicated",
     "checks": [
        {"id": "check_urp", "title": "查 under-replicated 分区数",
         "cmd": "kafka-topics.sh --bootstrap-server localhost:9092 --describe --under-replicated-partitions 2>/dev/null | grep -c Topic",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_broker"},
                      {"when": "output.value == 0", "goto": "done_no_urp"}],
         "otherwise": "check_broker",
         "cautions": ["under-replicated 说明有副本掉出 ISR——数据冗余降级，此时再挂一个 broker 就可能丢数据，"
                      "属高优先级问题"]},
        {"id": "check_broker", "title": "查 broker 是否有掉线/负载高",
         "cmd": "kafka-broker-api-versions.sh --bootstrap-server localhost:9092 2>/dev/null | grep -c 'id:'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_broker_lag"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["ISR 收缩三大因：follower 拉取跟不上(磁盘/网络慢)、broker GC 长停顿、"
                      "replica.lag.time.max.ms 配太小误判。别只重启 broker 了事"]},
     ],
     "dones": [
        {"id": "done_no_urp", "summary": "无 under-replicated 分区，副本健康。消费/生产问题另查。"},
        {"id": "done_broker_lag", "summary": "有副本不同步。定位掉出 ISR 的 follower 所在 broker，"
                                            "查其磁盘 IO/网络/GC；若是瞬时抖动可自愈，持续则扩容或优化该 broker。"},
     ]},
    {**_M,
     "id": "middleware.es.cluster-red", "name": "Elasticsearch 集群 Red/Yellow 排查",
     "taxonomy": "middleware/es/cluster-red",
     "symptom": "ES 集群状态 Red/Yellow/分片未分配/写入失败",
     "checks": [
        {"id": "check_health", "title": "查集群健康与未分配分片",
         "cmd": "curl -s localhost:9200/_cluster/health 2>/dev/null | grep -oE '\"unassigned_shards\":[0-9]+' | grep -oE '[0-9]+'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_reason"},
                      {"when": "output.value == 0", "goto": "done_healthy"}],
         "otherwise": "check_reason",
         "cautions": ["Red=有主分片未分配(该索引部分数据不可读写)；Yellow=副本分片未分配(数据在但冗余不足)。"
                      "Red 比 Yellow 严重得多，先救 Red"]},
        {"id": "check_reason", "title": "查分片未分配原因",
         "cmd": "curl -s 'localhost:9200/_cluster/allocation/explain' 2>/dev/null | grep -ic 'disk\\|watermark\\|NODE_LEFT\\|allocation'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_reason_found"},
                      {"when": "output.value == 0", "goto": "escalate"}],
         "otherwise": "escalate",
         "cautions": ["最常见未分配原因：磁盘超 watermark(默认 85%/90% 停止分配)、节点掉线、"
                      "分片数超节点限制。allocation/explain 会直接告诉你原因，别瞎猜"]},
     ],
     "dones": [
        {"id": "done_healthy", "summary": "无未分配分片，集群 Green。写入失败另查(mapping/线程池/限流)。"},
        {"id": "done_reason_found", "summary": "allocation/explain 已给出未分配原因。磁盘 watermark 满则清理/扩盘、"
                                             "节点掉线则恢复节点、分片超限则调 total_shards_per_node；对症处理后分片会自动分配。"},
     ]},
    {**_M,
     "id": "middleware.nginx.upstream-5xx", "name": "Nginx 上游 502/504 排查",
     "taxonomy": "middleware/nginx/upstream-5xx",
     "symptom": "Nginx 返回 502/504/upstream 连不上/网关错误",
     "checks": [
        {"id": "check_errlog", "title": "查 error log 的上游错误",
         "cmd": "tail -500 /var/log/nginx/error.log 2>/dev/null | grep -icE 'upstream|502|504|connect() failed|timed out'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "classify"},
                      {"when": "output.value == 0", "goto": "done_no_upstream_err"}],
         "otherwise": "classify",
         "cautions": ["Nginx 的 502/504 几乎都记在 error.log 且带明确原因(connection refused/timed out)——"
                      "先看日志，别从 access.log 的状态码倒推"]},
        {"id": "classify", "title": "区分连接被拒还是超时",
         "cmd": "tail -500 /var/log/nginx/error.log 2>/dev/null | grep -icE 'timed out|timeout'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_timeout"},
                      {"when": "output.value == 0", "goto": "done_refused"}],
         "otherwise": "escalate",
         "cautions": ["timed out=后端处理慢或没响应(504)；connection refused=后端没在监听/端口错(502)。"
                      "两者处置完全不同"]},
     ],
     "dones": [
        {"id": "done_no_upstream_err", "summary": "近期无上游错误。5xx 另查(Nginx 自身配置/限流/客户端)。"},
        {"id": "done_timeout", "summary": "上游超时(504)。查后端是否处理慢(扩容/优化)、"
                                         "或调大 proxy_read_timeout/proxy_connect_timeout(治标)。"},
        {"id": "done_refused", "summary": "上游连接被拒(502)。后端服务没起/端口不对/被防火墙挡——"
                                         "确认 upstream 配的地址端口与后端实际监听一致，后端进程健康。"},
     ]},
    {**_M,
     "id": "middleware.redis.slowlog-high", "name": "Redis 慢命令排查",
     "taxonomy": "middleware/redis/slowlog-high",
     "symptom": "Redis 响应慢/有慢命令/延迟高/客户端超时",
     "checks": [
        {"id": "check_slowlog", "title": "查慢日志条数",
         "cmd": "redis-cli slowlog len 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_bigkey"},
                      {"when": "output.value == 0", "goto": "done_no_slow"}],
         "otherwise": "check_bigkey",
         "cautions": ["slowlog 只记超过 slowlog-log-slower-than(默认 10ms)的命令；有条目说明确有慢命令，"
                      "但阈值配太大可能漏记"]},
        {"id": "check_bigkey", "title": "看是否存在大 key(慢命令常因)",
         "cmd": "redis-cli --bigkeys 2>/dev/null | grep -icE 'Biggest.*found|[0-9]{5,} '",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_bigkey"},
                      {"when": "output.value == 0", "goto": "done_slow_cmd"}],
         "otherwise": "escalate",
         "cautions": ["O(N) 命令(KEYS/HGETALL/SMEMBERS 大集合)是慢命令首因——尤其 KEYS 会阻塞整个实例。"
                      "禁用 KEYS、用 SCAN 替代"]},
     ],
     "dones": [
        {"id": "done_no_slow", "summary": "无慢日志。延迟高另查(网络/fork/内存换页)。"},
        {"id": "done_bigkey", "summary": "存在大 key，是慢命令的根源。拆分大 key(大 hash/set 分片)、"
                                        "避免对大 key 用 O(N) 命令；删除大 key 用 UNLINK(异步)而非 DEL。"},
        {"id": "done_slow_cmd", "summary": "有慢命令但非大 key 主导。slowlog get 看具体命令，"
                                          "禁用 KEYS 等 O(N) 命令、优化 Lua 脚本、避免大范围 ZRANGE。"},
     ]},
]
