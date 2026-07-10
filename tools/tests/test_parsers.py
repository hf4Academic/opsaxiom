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


# ---- Q-2 健康/派生字段解析器 ----
def test_health_parsers():
    assert parsers.get_parser("text/systemctl-active-v1")("active\ninactive")["service_active"] is True
    assert parsers.get_parser("text/systemctl-active-v1")("inactive\nfailed")["service_active"] is False
    mo = parsers.get_parser("text/mount-opts-v1")("ro,relatime\n[1.2] EXT4-fs error x")
    assert mo["mount_rw"] is False and mo["fs_errors"] == 1
    ct = parsers.get_parser("json/conntrack-v1")("95000\n100000")
    assert ct["ct_count"] == 95000 and ct["ct_max"] == 100000
    ro = parsers.get_parser("json/rollout-status-v1")("successfully rolled out\na Running true\nb Running false")
    assert ro["rollout_succeeded"] is True and ro["unready_pods"] == 1


def test_parser_field_declarations_present():
    # 6 个真实健康解析器都带字段声明
    for name in ["text/systemctl-active-v1", "json/systemctl-show-v1", "text/mount-opts-v1",
                 "json/conntrack-v1", "json/loadavg-v1", "json/rollout-status-v1"]:
        assert parsers.get_fields(name), f"{name} 缺字段声明"


def test_field_refs_ignores_strings_and_funcs():
    from exprlang import field_refs
    refs = dict(field_refs("count(rows[].path matches '/var/log') >= 1 and load1 > cores"))
    assert "rows" in refs and refs["rows"] == "path"
    assert "load1" in refs and "cores" in refs
    assert "count" not in refs        # 函数名不算字段
    assert "var" not in refs          # 字符串字面量内的词不算字段
