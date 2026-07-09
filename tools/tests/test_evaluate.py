"""求值器单元测试（O-6 运行时核心）。"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from exprlang import evaluate as ev  # noqa: E402

CTX = {
    "rows": [{"pcent": 95, "path": "/var/log/a.log"}, {"pcent": 10, "path": "/data"}],
    "output": {"value": 300}, "mount": {"size": 1000},
    "state": "Established", "prefixes": 100, "baseline": 100,
}


@pytest.mark.parametrize("expr,expected", [
    ("rows[0].pcent >= 90", True),
    ("rows[0].pcent < 90", False),
    ("rows[1].pcent < 90", True),
    ("output.value > mount.size * 0.2", True),         # 300 > 200
    ("output.value < mount.size * 0.2", False),
    ("max(rows[].pcent) > 90", True),
    ("min(rows[].pcent) > 90", False),
    ("count(rows[].pcent > 50) >= 1", True),           # 只有 95 > 50
    ("count(rows[].pcent > 50) >= 2", False),
    ("count(rows[].path matches '/var/log') >= 1", True),
    ("count(rows) == 2", True),
    ("any(rows[].pcent > 90)", True),
    ("all(rows[].pcent > 90)", False),
    ("state == 'Established' and prefixes >= baseline * 0.9", True),
    ("state == 'Idle'", False),
    ("not (state == 'Idle')", True),
])
def test_eval(expr, expected):
    assert bool(ev(expr, CTX)) == expected


def test_missing_field_is_falsey():
    # 缺失字段 → None → 分支不成立（走 otherwise）
    assert bool(ev("nonexistent > 5", CTX)) is False
    assert ev("nonexistent", CTX) is None


def test_delta_reads_context():
    ctx = {"input_errors": 5, "__delta__": {"input_errors": 12}}
    assert bool(ev("delta(input_errors, 60s) > 0", ctx)) is True
    assert bool(ev("delta(input_errors, 60s) > 20", ctx)) is False


def test_avg_sum():
    ctx = {"rows": [{"v": 10}, {"v": 20}, {"v": 30}]}
    assert ev("avg(rows[].v) == 20", ctx)
    assert ev("sum(rows[].v) == 60", ctx)
    assert ev("avg(rows[].v) > 15", ctx)


def test_avg_sum_legal_in_validator():
    from exprlang import validate_when
    assert validate_when("avg(rows[].wa) > 20")[0]
    assert validate_when("sum(rows[].bytes) > 1000")[0]


def test_parse_template_ref():
    from exprlang import parse_template_ref
    assert parse_template_ref("mount") == (True, "mount", None)
    assert parse_template_ref("rows[0].comm")[:2] == (True, "rows")
    assert parse_template_ref("discovery.free.avail") == (True, "discovery", "free")
    ok, _, _ = parse_template_ref("count(rows)")     # 函数非法
    assert not ok
    ok, _, _ = parse_template_ref("a|b")             # | 非法
    assert not ok
