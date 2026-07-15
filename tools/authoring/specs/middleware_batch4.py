"""H-push middleware 域批量 spec（第四批）——Redis Cluster/Kafka/PostgreSQL/Nginx。"""

_M = {"capability_level": "read", "connector": "ssh"}

SPECS = [
    {**_M,
     "id": "middleware.redis.cluster-down", "name": "Redis Cluster 槽位未覆盖排查",
     "taxonomy": "middleware/redis/cluster-down",
     "symptom": "Redis Cluster 报 CLUSTERDOWN/部分 key 访问失败/槽位未覆盖/hash slot not served",
     "checks": [
        {"id": "check_state", "title": "查集群状态是否 ok",
         "cmd": "redis-cli cluster info 2>/dev/null | grep -c 'cluster_state:fail'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_slots"},
                      {"when": "output.value == 0", "goto": "done_state_ok"}],
         "otherwise": "check_slots",
         "cautions": ["cluster_state:fail=有槽位没有主节点提供服务,整个集群拒绝相关请求;默认配置下只要有一个槽"
                      "无人负责,cluster-require-full-coverage 就让全集群不可写——一个分片挂能拖垮全局"]},
        {"id": "check_slots", "title": "查已分配的槽位数是否满 16384",
         "cmd": "redis-cli cluster info 2>/dev/null | awk -F: '/cluster_slots_assigned/{print \"assigned\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.assigned < 16384", "goto": "done_slots_missing"},
                      {"when": "output.assigned >= 16384", "goto": "done_all_assigned"}],
         "otherwise": "escalate",
         "cautions": ["16384 个槽必须全部有主负责集群才 ok;缺槽多因某主节点宕机且无从可升、或 reshard 中断;"
                      "cluster_slots_assigned < 16384 直接点出缺了多少槽"]},
     ],
     "dones": [
        {"id": "done_state_ok", "summary": "集群状态 ok。部分 key 失败另查(客户端未处理 MOVED/ASK 重定向、连错节点、大 key 超时)。"},
        {"id": "done_slots_missing", "summary": "有槽位未分配(集群 fail)。查负责缺失槽的主节点是否宕机——恢复它或把其从"
                                             "升为主(cluster failover);reshard 中断则续做迁移把槽补齐,集群才恢复。"},
        {"id": "done_all_assigned", "summary": "槽位已满但状态曾 fail,可能是从节点视角或瞬时。在多个节点确认 cluster_state,"
                                            "检查节点间连通(cluster bus 端口)与 pfail/fail 标记,排查网络分区。"},
     ]},
    {**_M,
     "id": "middleware.kafka.log-disk-full", "name": "Kafka 磁盘满/日志段堆积排查",
     "taxonomy": "middleware/kafka/log-disk-full",
     "symptom": "Kafka broker 磁盘满/无法写入/log dir offline/broker 下线",
     "checks": [
        {"id": "check_disk", "title": "查 Kafka 数据目录磁盘使用",
         "cmd": "df /var/lib/kafka /data/kafka 2>/dev/null | awk 'NR>1{gsub(/%/,\"\",$5); if($5>m)m=$5} END{print m+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 85", "goto": "check_retention"},
                      {"when": "output.value <= 85", "goto": "done_disk_ok"}],
         "otherwise": "check_retention",
         "cautions": ["Kafka 磁盘满会让对应 log dir 下线,该 broker 上的分区不可用;别直接删 .log 段文件——"
                      "会破坏索引和副本一致性,要通过调 retention 让 Kafka 自己清"]},
        {"id": "check_retention", "title": "看是否有超大 topic 占满盘",
         "cmd": "du -s /var/lib/kafka/* /data/kafka/* 2>/dev/null | sort -rn | head -1 | awk '{print int($1/1048576)}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 50", "goto": "done_big_topic"},
                      {"when": "output.value <= 50", "goto": "done_general_full"}],
         "otherwise": "escalate",
         "cautions": ["单 topic 占盘巨大多因 retention 设太长/无限、或该 topic 写入量远超预期;调小 retention.ms/"
                      "retention.bytes 让旧段被清,是安全的降盘手段(别手删文件)"]},
     ],
     "dones": [
        {"id": "done_disk_ok", "summary": "Kafka 磁盘未满。写入失败另查(broker/controller 状态、ISR、副本、ZK/KRaft 元数据)。"},
        {"id": "done_big_topic", "summary": "某 topic 占盘过大撑满磁盘。对其调小 retention.ms/retention.bytes 触发清理,"
                                         "或扩盘/迁移分区;确认写入量是否异常(生产端暴增)。别手动删段文件。"},
        {"id": "done_general_full", "summary": "磁盘普遍占满,非单 topic 独大。整体缩短 retention、扩容磁盘、或增加 broker"
                                            "分摊分区;恢复空间后被 offline 的 log dir 需按流程重新上线。"},
     ]},
    {**_M,
     "id": "middleware.postgres.replication-slot-bloat", "name": "PostgreSQL 复制槽导致 WAL 撑盘排查",
     "taxonomy": "middleware/postgres/replication-slot-bloat",
     "symptom": "PG 的 pg_wal 目录暴涨/磁盘满/WAL 不回收/有废弃复制槽",
     "checks": [
        {"id": "check_slots", "title": "查是否有非活跃复制槽",
         "cmd": "psql -tAc \"SELECT count(*) FROM pg_replication_slots WHERE active='f'\" 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_lag"},
                      {"when": "output.value == 0", "goto": "done_no_dead_slot"}],
         "otherwise": "check_lag",
         "cautions": ["复制槽会让主库保留下游还没消费的 WAL——下游(从库/逻辑订阅)掉了但槽还在,主库就一直不敢删 WAL,"
                      "pg_wal 无限膨胀直到撑爆磁盘;废弃的 inactive 槽是撑盘头号元凶"]},
        {"id": "check_lag", "title": "查槽滞留的 WAL 大小",
         "cmd": "psql -tAc \"SELECT COALESCE(max(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))/1048576,0)::int FROM pg_replication_slots\" 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1024", "goto": "done_slot_bloat"},
                      {"when": "output.value <= 1024", "goto": "done_slot_ok"}],
         "otherwise": "escalate",
         "cautions": ["槽滞留 WAL 很大=下游远远落后或已死;确认该槽对应的下游是否还需要——真废弃就 drop 掉释放 WAL,"
                      "别设 max_slot_wal_keep_size 之外还留着僵尸槽"]},
     ],
     "dones": [
        {"id": "done_no_dead_slot", "summary": "无非活跃复制槽。pg_wal 涨另查(checkpoint 间隔、archive_command 卡住没归档成功、"
                                            "wal 生成量突增)。"},
        {"id": "done_slot_bloat", "summary": "非活跃复制槽滞留大量 WAL 撑盘。确认对应下游确已废弃后 pg_drop_replication_slot"
                                          "删除该槽,WAL 即可回收;设 max_slot_wal_keep_size 兜底防复发。"},
        {"id": "done_slot_ok", "summary": "有非活跃槽但滞留 WAL 不大。观察下游是否会重连消费;短期掉线可等其恢复,"
                                       "长期不用则清理该槽,避免日后堆积。"},
     ]},
    {**_M,
     "id": "middleware.nginx.reload-fail", "name": "Nginx 配置 reload 失败排查",
     "taxonomy": "middleware/nginx/reload-fail",
     "symptom": "nginx reload 报错/新配置不生效/reload 后还是旧配置/配置测试不通过",
     "checks": [
        {"id": "check_test", "title": "查配置语法测试是否通过",
         "cmd": "nginx -t 2>&1 | grep -ic 'test failed\\|emerg\\|unexpected\\|unknown directive'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_syntax_err"},
                      {"when": "output.value == 0", "goto": "check_master"}],
         "otherwise": "check_master",
         "cautions": ["reload 前 Nginx 会先测配置,测不过就拒绝加载、继续用旧配置(这是保护,服务不中断);"
                      "'改了不生效'第一件事就是 nginx -t 看新配置到底有没有语法/引用错误"]},
        {"id": "check_master", "title": "看 master 进程是否在运行",
         "cmd": "pgrep -c -f 'nginx: master' 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_reload_ok"},
                      {"when": "output.value == 0", "goto": "done_no_master"}],
         "otherwise": "escalate",
         "cautions": ["reload 靠给 master 发 HUP 信号;master 没跑(或 reload 命令发给了错的实例)自然不生效;"
                      "确认是对正确的 master 进程做 reload,systemd 管理的用 systemctl reload"]},
     ],
     "dones": [
        {"id": "done_syntax_err", "summary": "配置语法测试不通过,reload 被拒(仍用旧配置)。按 nginx -t 报错定位行修复"
                                          "(常见:分号缺失、指令拼错、引用的证书/upstream 文件不存在),修好再 reload。"},
        {"id": "done_no_master", "summary": "Nginx master 进程未运行,reload 无对象。这已不是 reload 问题——先 start 起 Nginx;"
                                         "查它为何没跑(上次启动失败/被 kill/端口占用)。"},
        {"id": "done_reload_ok", "summary": "配置测试通过且 master 在跑,reload 应已生效。若仍是旧行为,确认改的是被 include"
                                         "的正确文件、是否有多实例、浏览器/上游缓存;必要时用 systemctl reload 再触发一次。"},
     ]},
]
