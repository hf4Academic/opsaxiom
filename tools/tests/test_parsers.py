"""O-5 解析器测试。"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import parsers  # noqa: E402


def test_df_parser():
    text = """Filesystem      Size    Used   Avail Use%
/dev/sda1  10737418240  9663676416  1073741824  90%
/data      53687091200  10737418240  42949672960  20%"""
    out = parsers.get_parser("table/df-v1")(text)
    rows = out["rows"]
    assert len(rows) == 2
    assert rows[0]["pcent"] == 90
    assert rows[0]["target"] == "/dev/sda1"
    assert rows[1]["pcent"] == 20


def test_df_inode_parser():
    text = """Filesystem       Inodes  IUsed IUse%
/dev/sda1        655360  655000  99%
/data           1000000   50000   5%"""
    rows = parsers.get_parser("table/df-inode-v1")(text)["rows"]
    assert rows[0]["ipcent"] == 99
    assert rows[1]["ipcent"] == 5


def test_du_parser():
    text = "10737418240\t/var/log\n5368709120\t/var/lib/docker\n"
    rows = parsers.get_parser("table/du-v1")(text)["rows"]
    assert rows[0]["size"] == 10737418240
    assert rows[0]["path"] == "/var/log"
    assert len(rows) == 2


def test_unknown_parser_returns_none():
    assert parsers.get_parser("table/does-not-exist") is None


def test_ntc_wrapper_degrades_gracefully():
    # 未安装 ntc-templates 时不应崩溃，返回占位结构
    p = parsers.get_parser("ntc/cisco_ios/bgp-summary")
    assert p is not None
    out = p("BGP router identifier 1.1.1.1\n")
    assert "rows" in out
