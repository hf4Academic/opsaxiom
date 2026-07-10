"""T-2 症状匹配测试。"""
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import diagnose

IDX = diagnose.load_index()

CASES = [
    ("磁盘满了 No space left", "host.storage.capacity.disk-full"),
    ("pod 一直重启 CrashLoopBackOff", "k8s.workload.crashloop"),
    ("BGP 邻居 down 了", "network.routing.bgp.neighbor-down"),
    ("mysql 主从延迟很大", "middleware.mysql.replication-lag"),
    ("redis 有个大key阻塞", "middleware.redis.bigkey"),
    ("接口光衰 收光低", "network.physical.optic-fault"),
]


@pytest.mark.parametrize("query,expect_id", CASES)
def test_top_match(query, expect_id):
    hits = diagnose.match(query, idx=IDX, top=3)
    assert hits, f"无匹配: {query}"
    assert hits[0][1]["id"] == expect_id, \
        f"{query} 期望 {expect_id}，实际 {[h[1]['id'] for h in hits]}"


def test_no_match_returns_empty():
    assert diagnose.match("今天天气不错", idx=IDX) == []
