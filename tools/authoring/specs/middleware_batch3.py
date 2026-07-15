"""H-push middleware 域批量 spec（第三批）——拓宽引擎:PostgreSQL/Redis/Kafka/ZooKeeper/MongoDB/HAProxy。"""

_M = {"capability_level": "read", "connector": "ssh"}

SPECS = [
    {**_M,
     "id": "middleware.postgres.connection-exhausted", "name": "PostgreSQL 连接耗尽排查",
     "taxonomy": "middleware/postgres/connection-exhausted",
     "symptom": "PG 报 too many clients/连不上/remaining connection slots reserved",
     "checks": [
        {"id": "check_used", "title": "查当前连接数",
         "cmd": "psql -tAc 'SELECT count(*) FROM pg_stat_activity' 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 90", "goto": "check_idle"},
                      {"when": "output.value <= 90", "goto": "done_conn_ok"}],
         "otherwise": "check_idle",
         "cautions": ["PG 每个连接是一个进程,连接数打满不只是拒新连,还很吃内存;"
                      "max_connections 调太大反而伤性能——正解常是前面挂连接池(pgbouncer)而非一味调大"]},
        {"id": "check_idle", "title": "看有多少是 idle in transaction 僵连接",
         "cmd": "psql -tAc \"SELECT count(*) FROM pg_stat_activity WHERE state='idle in transaction'\" 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_idle_in_txn"},
                      {"when": "output.value == 0", "goto": "done_real_load"}],
         "otherwise": "escalate",
         "cautions": ["'idle in transaction'=开了事务不提交也不回滚,既占连接又持锁还阻塞 vacuum——"
                      "多为应用忘了 commit 或连接池归还前没结束事务,是连接被白占的头号原因"]},
     ],
     "dones": [
        {"id": "done_conn_ok", "summary": "连接数不高。连不上另查(网络/pg_hba 认证/监听地址/服务是否在跑)。"},
        {"id": "done_idle_in_txn", "summary": "大量 idle in transaction 僵连接占满槽位。定位来源应用修复其事务收尾"
                                           "(及时 commit/rollback)、设 idle_in_transaction_session_timeout 兜底;前置 pgbouncer 复用连接。"},
        {"id": "done_real_load", "summary": "连接确为真实活跃负载打满。前面加连接池(pgbouncer)复用、优化慢查询缩短占用、"
                                         "评估后适度上调 max_connections(注意内存);别让每个客户端直连吃满进程数。"},
     ]},
    {**_M,
     "id": "middleware.postgres.autovacuum-lag", "name": "PostgreSQL 表膨胀/autovacuum 滞后排查",
     "taxonomy": "middleware/postgres/autovacuum-lag",
     "symptom": "PG 表膨胀/查询越来越慢/磁盘涨/事务ID回卷告警/autovacuum 跟不上",
     "checks": [
        {"id": "check_deadtup", "title": "查死元组最多的表",
         "cmd": "psql -tAc 'SELECT max(n_dead_tup) FROM pg_stat_user_tables' 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 100000", "goto": "check_wraparound"},
                      {"when": "output.value <= 100000", "goto": "done_bloat_ok"}],
         "otherwise": "check_wraparound",
         "cautions": ["死元组(update/delete 留下的旧版本)堆积=表膨胀,查询要扫更多页变慢;autovacuum 清不过来"
                      "多因高频写、autovacuum 太保守、或长事务挡住回收"]},
        {"id": "check_wraparound", "title": "查事务ID年龄(回卷风险)",
         "cmd": "psql -tAc 'SELECT max(age(datfrozenxid)) FROM pg_database' 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 1000000000", "goto": "done_wraparound_risk"},
                      {"when": "output.value <= 1000000000", "goto": "done_tune_autovacuum"}],
         "otherwise": "escalate",
         "cautions": ["事务ID年龄接近 20 亿会触发回卷保护,PG 为防数据损坏会强制停止写入——这是可导致全库不可写的"
                      "严重事故;age 高时必须尽快 vacuum(freeze),别拖"]},
     ],
     "dones": [
        {"id": "done_bloat_ok", "summary": "死元组不多,膨胀不明显。变慢另查(缺索引/统计信息过期需 ANALYZE/查询本身重)。"},
        {"id": "done_wraparound_risk", "summary": "事务ID年龄偏高,有回卷风险(严重)。尽快对高龄表 VACUUM(FREEZE),"
                                               "排查是否有长事务/未提交 prepared transaction 挡住 freeze;这是高优先级隐患。"},
        {"id": "done_tune_autovacuum", "summary": "膨胀明显但暂无回卷风险。对膨胀表手动 VACUUM、调激进 autovacuum 参数"
                                               "(降 scale_factor、提 max_workers/成本上限)、清理长事务;必要时 pg_repack 在线整理。"},
     ]},
    {**_M,
     "id": "middleware.redis.replication-break", "name": "Redis 主从复制中断排查",
     "taxonomy": "middleware/redis/replication-break",
     "symptom": "Redis 从库数据不更新/主从断开/master_link_status down/读到旧数据",
     "checks": [
        {"id": "check_link", "title": "查从库到主的复制链路状态",
         "cmd": "redis-cli info replication 2>/dev/null | grep -c 'master_link_status:down'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_backlog"},
                      {"when": "output.value == 0", "goto": "done_link_up"}],
         "otherwise": "check_backlog",
         "cautions": ["master_link_status:down=从库当前连不上主;区分是网络断、认证(masterauth)错、"
                      "还是主库负载高拒绝同步——info 的 master_last_io_seconds_ago 能看多久没通信了"]},
        {"id": "check_backlog", "title": "看是否频繁全量重同步",
         "cmd": "redis-cli info stats 2>/dev/null | awk -F: '/sync_full/{print \"full\", $2}'",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.full > 3", "goto": "done_full_resync"},
                      {"when": "output.full <= 3", "goto": "done_link_flap"}],
         "otherwise": "escalate",
         "cautions": ["sync_full 频繁增长=一直在做代价高昂的全量同步(而非增量)——多因复制积压缓冲区"
                      "(repl-backlog-size)太小,断连稍久就只能全量;调大 backlog 可让短暂断连走增量"]},
     ],
     "dones": [
        {"id": "done_link_up", "summary": "主从链路正常(up)。从库读到旧数据另查(复制延迟/客户端连错节点/一致性预期)。"},
        {"id": "done_full_resync", "summary": "频繁全量重同步,代价高且期间从库不可用。调大主库 repl-backlog-size 与"
                                           "repl-backlog-ttl 让短断连走增量;排查网络抖动根因,别让它反复断。"},
        {"id": "done_link_flap", "summary": "链路 down 但非频繁全量,当前是断开态。查网络连通、masterauth 是否正确、"
                                         "主库是否内存/负载过高拒绝同步;主恢复后观察 master_link_status 是否回 up。"},
     ]},
    {**_M,
     "id": "middleware.kafka.rebalance-storm", "name": "Kafka 消费组频繁 rebalance 排查",
     "taxonomy": "middleware/kafka/rebalance-storm",
     "symptom": "消费组频繁 rebalance/消费卡顿/consumer 反复加入离开/消费停滞",
     "checks": [
        {"id": "check_rebalance", "title": "查消费者日志里的 rebalance 频次",
         "cmd": "tail -1000 /var/log/kafka/consumer.log 2>/dev/null | grep -ic 'Rebalancing\\|Revoke partitions\\|Attempt.*join group'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 10", "goto": "check_timeout"},
                      {"when": "output.value <= 10", "goto": "done_rebalance_ok"}],
         "otherwise": "check_timeout",
         "cautions": ["每次 rebalance 期间整组消费都暂停(stop-the-world),频繁 rebalance=消费一直在停停走走;"
                      "根因多是消费者被判定'掉线'反复踢出再加入"]},
        {"id": "check_timeout", "title": "看是否因处理慢触发会话/轮询超时",
         "cmd": "tail -1000 /var/log/kafka/consumer.log 2>/dev/null | grep -ic 'max.poll.interval\\|session.timeout\\|leaving group'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_poll_slow"},
                      {"when": "output.value == 0", "goto": "done_member_flap"}],
         "otherwise": "escalate",
         "cautions": ["单批消息处理时间超过 max.poll.interval.ms,消费者来不及下次 poll 就被判死踢出,触发 rebalance;"
                      "越踢越慢形成风暴。调大该参数或减小 max.poll.records 是常见解"]},
     ],
     "dones": [
        {"id": "done_rebalance_ok", "summary": "rebalance 不频繁。消费卡顿另查(分区 Leader 变动/broker 负载/生产端积压)。"},
        {"id": "done_poll_slow", "summary": "处理慢导致轮询/会话超时被踢触发 rebalance。调大 max.poll.interval.ms、"
                                         "减小 max.poll.records 让单批更快处理完,或异步化重逻辑;稳住后 rebalance 平息。"},
        {"id": "done_member_flap", "summary": "成员反复进出但非 poll 超时,查消费者实例是否频繁重启/GC 长停顿/网络抖动"
                                           "导致心跳丢失;稳定消费者进程与到 broker 的网络,必要时调 session.timeout.ms。"},
     ]},
    {**_M,
     "id": "middleware.zookeeper.quorum-loss", "name": "ZooKeeper 失去多数派排查",
     "taxonomy": "middleware/zookeeper/quorum-loss",
     "symptom": "ZK 集群不可用/no quorum/依赖 ZK 的服务(Kafka/HBase)集体异常",
     "checks": [
        {"id": "check_mode", "title": "查本节点 ZK 角色是否正常",
         "cmd": "echo srvr | nc -w2 localhost 2181 2>/dev/null | grep -ic 'Mode: leader\\|Mode: follower'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_followers"},
                      {"when": "output.value == 0", "goto": "done_no_role"}],
         "otherwise": "check_followers",
         "cautions": ["ZK 靠多数派(quorum)选主:5 节点挂 3 就没 quorum,整个集群拒绝写、只能只读甚至不可用;"
                      "先确认本节点是 leader/follower 还是掉成了 looking(选不出主)"]},
        {"id": "check_followers", "title": "查 leader 视角的存活 follower 数",
         "cmd": "echo mntr | nc -w2 localhost 2181 2>/dev/null | awk -F'\\t' '/zk_followers|zk_synced_followers/{print \"followers\", $2}' | head -1",
         "parser": "generic/kv-num-v1",
         "branches": [{"when": "output.followers > 0", "goto": "done_quorum_ok"},
                      {"when": "output.followers == 0", "goto": "done_isolated"}],
         "otherwise": "escalate",
         "cautions": ["同步的 follower 数决定 quorum 是否成立;数量不足要逐个查挂掉的 ZK 节点"
                      "(进程/磁盘/网络分区),别只重启本节点了事"]},
     ],
     "dones": [
        {"id": "done_no_role", "summary": "本节点无正常角色(可能 looking/不可用)。查本节点 ZK 进程与日志、"
                                       "myid/zoo.cfg 配置、到其它节点网络;它选不出主往往因多数节点已失联。"},
        {"id": "done_quorum_ok", "summary": "本节点有角色且有同步 follower,quorum 大体成立。依赖服务异常另查其自身"
                                         "到 ZK 的连接/会话超时;若曾抖动,核对各节点稳定性。"},
        {"id": "done_isolated", "summary": "疑似 quorum 不足(无同步 follower)。逐个恢复挂掉的 ZK 节点(进程/磁盘/网络分区),"
                                        "凑够多数派集群才恢复可写;检查是否网络分区把集群切成了少数派。"},
     ]},
    {**_M,
     "id": "middleware.mongodb.replica-lag", "name": "MongoDB 副本集延迟排查",
     "taxonomy": "middleware/mongodb/replica-lag",
     "symptom": "Mongo 从节点延迟大/读到旧数据/secondary 落后/选举风险",
     "checks": [
        {"id": "check_lag", "title": "查从节点复制延迟(秒)",
         "cmd": "mongosh --quiet --eval 'rs.status().members.filter(m=>m.state==2).map(m=>m.optimeDate).forEach(d=>print(Math.round((rs.status().date-d)/1000)))' 2>/dev/null | sort -rn | head -1",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 30", "goto": "check_health"},
                      {"when": "output.value <= 30", "goto": "done_lag_ok"}],
         "otherwise": "check_health",
         "cautions": ["副本延迟大=从节点数据落后主节点;延迟内的 secondary 读会读到旧数据,且主挂时延迟太大的从"
                      "选上来会丢数据。先看延迟秒数再定严重性"]},
        {"id": "check_health", "title": "看从节点是否健康(非 down/recovering)",
         "cmd": "mongosh --quiet --eval 'print(rs.status().members.filter(m=>m.health!=1||m.state==3||m.state==6).length)' 2>/dev/null",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "done_member_unhealthy"},
                      {"when": "output.value == 0", "goto": "done_slow_apply"}],
         "otherwise": "escalate",
         "cautions": ["从节点 RECOVERING/不健康会持续落后甚至掉出副本集;区分是节点本身有病(磁盘/网络/正在初始同步)"
                      "还是只是应用 oplog 慢跟不上写入速度"]},
     ],
     "dones": [
        {"id": "done_lag_ok", "summary": "副本延迟在可接受范围。读到旧数据可能是 readPreference=secondary 的预期行为;"
                                       "需强一致就读 primary 或设 readConcern。"},
        {"id": "done_member_unhealthy", "summary": "有从节点不健康(down/recovering)导致落后。查该节点磁盘/网络/是否在初始同步,"
                                                "恢复其健康;长期跟不上考虑重做初始同步或扩其资源。"},
        {"id": "done_slow_apply", "summary": "节点健康但 oplog 应用跟不上写入(延迟大)。查从节点磁盘 IO/负载是否成瓶颈、"
                                          "主库写入是否突增;必要时升级从节点硬件或分流读负载,缩小延迟窗口。"},
     ]},
    {**_M,
     "id": "middleware.haproxy.backend-down", "name": "HAProxy 后端不可用排查",
     "taxonomy": "middleware/haproxy/backend-down",
     "symptom": "HAProxy 报 503/后端全挂/no server available/健康检查全 DOWN",
     "checks": [
        {"id": "check_down", "title": "查 DOWN 状态的后端数",
         "cmd": "echo 'show stat' | socat stdio /run/haproxy/admin.sock 2>/dev/null | awk -F, '$18==\"DOWN\"{c++} END{print c+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value > 0", "goto": "check_up"},
                      {"when": "output.value == 0", "goto": "done_all_up"}],
         "otherwise": "check_up",
         "cautions": ["后端 DOWN 是 HAProxy 主动健康检查判定的;先分清是后端真挂了,还是健康检查配置本身有问题"
                      "(检查路径/端口/超时不对)把好的也判成 DOWN"]},
        {"id": "check_up", "title": "看是否还有存活后端",
         "cmd": "echo 'show stat' | socat stdio /run/haproxy/admin.sock 2>/dev/null | awk -F, '$18==\"UP\"{c++} END{print c+0}'",
         "parser": "generic/count-v1",
         "branches": [{"when": "output.value == 0", "goto": "done_all_down"},
                      {"when": "output.value > 0", "goto": "done_partial_down"}],
         "otherwise": "escalate",
         "cautions": ["一个存活后端都没有=前端必然 503;此时优先恢复至少一个后端保住可用性,再从容排查其余"]},
     ],
     "dones": [
        {"id": "done_all_up", "summary": "后端均 UP。仍报 503 另查(前端 maxconn/ACL 路由/后端返回的真 503/超时配置)。"},
        {"id": "done_all_down", "summary": "后端全 DOWN,前端必然 503(高优先)。核实后端服务是否真挂(逐个直连测),"
                                        "同时排查是否健康检查配置误判;先拉起一个后端恢复服务,再补齐其余。"},
        {"id": "done_partial_down", "summary": "部分后端 DOWN,容量下降有过载风险。逐个查 DOWN 后端(进程/端口/网络),"
                                            "或核对健康检查参数是否过严误判;恢复后端数量到能承载流量的水平。"},
     ]},
]
