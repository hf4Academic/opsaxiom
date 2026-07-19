"""I-8 linkbook 测试：段级前缀匹配 / 聚合去重 / 全局键 / 缺失优雅。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import linkbook  # noqa: E402

BOOK = {
    "middleware/mysql": [
        {"name": "MySQL 慢查询大盘", "url": "https://g.corp/mysql"},
        {"name": "DB 值班表", "url": "https://w.corp/db-oncall"},
    ],
    "middleware": [{"name": "中间件总览", "url": "https://g.corp/mw"}],
    "k8s": [{"name": "集群总览", "url": "https://g.corp/k8s"}],
    "*": [{"name": "事件通报指引", "url": "https://w.corp/howto"}],
}


def test_longest_prefix_and_aggregate():
    ls = linkbook.links_for(["middleware/mysql/slow-query-storm"], book=BOOK)
    urls = [l["url"] for l in ls]
    # 命中 middleware/mysql（更具体，靠前）+ middleware（一般）+ *（全局，垫底）
    assert urls == ["https://g.corp/mysql", "https://w.corp/db-oncall",
                    "https://g.corp/mw", "https://w.corp/howto"]


def test_segment_boundary_no_false_match():
    # 键 middleware/mysql 不应命中 middleware/mysqld-exporter（段级，非字符级）
    ls = linkbook.links_for(["middleware/mysqld-exporter/down"], book=BOOK)
    urls = [l["url"] for l in ls]
    assert "https://g.corp/mysql" not in urls          # mysql != mysqld-exporter
    assert "https://g.corp/mw" in urls                 # middleware 前缀仍命中
    assert "https://w.corp/howto" in urls              # 全局仍在


def test_global_only_when_no_domain_match():
    ls = linkbook.links_for(["network/routing/bgp-max-prefix"], book=BOOK)
    assert [l["url"] for l in ls] == ["https://w.corp/howto"]


def test_dedup_across_taxonomies():
    ls = linkbook.links_for(
        ["middleware/mysql/a", "middleware/redis/b"], book=BOOK)
    urls = [l["url"] for l in ls]
    assert len(urls) == len(set(urls))                 # 全局与 middleware 不重复计


def test_missing_file_graceful(tmp_path):
    assert linkbook.load(tmp_path / "nope.yaml") == {}
    assert linkbook.links_for(["k8s/x"], book={}) == []
    assert linkbook.render_line(["k8s/x"], book={}) == ""


def test_render_line(tmp_path):
    line = linkbook.render_line(["k8s/workload/crashloop"], book=BOOK)
    assert line.startswith("📌 你的相关页面：")
    assert "集群总览" in line and "事件通报指引" in line


def test_load_from_disk(tmp_path):
    f = tmp_path / "linkbook.yaml"
    f.write_text(yaml.safe_dump({"links": BOOK}, allow_unicode=True), encoding="utf-8")
    book = linkbook.load(f)
    assert "middleware/mysql" in book
