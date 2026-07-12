"""Z-1 环境事实库测试：命中跳过 / 过期重取 / 跨 Skill 复用 + 证据链 + 归档。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import facts as F  # noqa: E402


def test_put_and_hit_skips_reexec():
    """命中跳过：入库后同命令查库即得解析产物，无需再执行。"""
    st = F.FactStore()
    parsed = {"rows": [{"target": "/data", "pcent": 92}],
              "output": {"pcent": 92}}
    st.put_parsed("df -B1 --output=target,size,used,avail,pcent /data",
                  parsed, now=1000.0)
    # 同命令（含多余空格，归一化后同）→ 命中
    got = st.get_parsed("df -B1 --output=target,size,used,avail,pcent   /data",
                        now=1100.0)
    assert got == parsed
    assert st.has("df -B1 --output=target,size,used,avail,pcent /data", now=1100.0)


def test_expired_forces_recollect():
    """过期重取：超过 TTL 后查库返回 None，逼调用方重新采集。"""
    st = F.FactStore(default_ttl=300)
    st.put_parsed("df -i /data", {"output": {"ipcent": 100}}, now=1000.0)
    assert st.get_parsed("df -i /data", now=1200.0) is not None      # 200s 内存活
    assert st.get_parsed("df -i /data", now=1400.0) is None          # 400s 已过期
    assert not st.has("df -i /data", now=1400.0)


def test_cross_skill_reuse_same_command():
    """跨 Skill 复用：Skill A 采的 df，Skill B 同命令直接命中（同 store 即同 incident）。"""
    st = F.FactStore()
    st.put_parsed("df -B1 --output=pcent /var", {"output": {"pcent": 95}},
                  now=500.0)
    # Skill B 想跑同一条只读命令 → 命中，跳过
    assert st.get_field("pcent", "df -B1 --output=pcent /var", now=600.0) == 95


def test_target_isolation():
    """不同 target 不串：本机的 df 不能命中远端设备的同名命令。"""
    st = F.FactStore()
    st.put_parsed("df -h /", {"output": {"pcent": 80}}, target="local", now=1.0)
    assert st.get_parsed("df -h /", target="local", now=2.0) is not None
    assert st.get_parsed("df -h /", target="switch-a", now=2.0) is None


def test_evidence_ledger_has_provenance():
    """证据链：标量事实带 source_cmd/field/value，BUNDLE 不进证据清单。"""
    st = F.FactStore()
    st.put_parsed("df -i /data", {"rows": [{"x": 1}], "output": {"ipcent": 100}},
                  parser="table/df-inode-v1", now=1000.0)
    ev = st.evidence(now=1000.0)
    assert any(e["field"] == "ipcent" and e["value"] == 100 for e in ev)
    assert all(e["field"] != "*" for e in ev)             # BUNDLE 不是证据
    e = next(e for e in ev if e["field"] == "ipcent")
    assert e["source_cmd"] == "df -i /data"               # 出处可追溯


def test_scalars_flattened_from_output_namespace():
    """output.* 里的标量要被提成独立事实（分支判据主力）。"""
    st = F.FactStore()
    st.put_parsed("cmd", {"output": {"value": 42}, "rows": [], "lines": ["a"]},
                  now=1.0)
    assert st.get_field("value", "cmd", now=1.0) == 42


def test_save_load_drops_expired(tmp_path):
    """归档往返：save→load 恢复存活事实，过期的在 load 时丢弃。"""
    st = F.FactStore(default_ttl=300)
    st.put_parsed("df -h /", {"output": {"pcent": 70}}, now=1000.0)
    p = st.save(tmp_path / "facts.json")
    # 存活期内加载 → 命中
    st2 = F.FactStore().load(p, now=1100.0)
    assert st2.get_field("pcent", "df -h /", now=1100.0) == 70
    # 过期后加载 → 丢弃
    st3 = F.FactStore().load(p, now=1500.0)
    assert st3.get_parsed("df -h /", now=1500.0) is None
