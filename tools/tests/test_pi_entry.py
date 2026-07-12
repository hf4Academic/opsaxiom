"""N-3 入口探测测试：node 版本门 / pi 发现 / 缺口诚实报告。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import pi_entry  # noqa: E402


def test_node_version_gate(monkeypatch):
    """node < 22.19 不算数（pi TUI 的 /v 正则要新 node）。"""
    monkeypatch.setattr(pi_entry, "_node_version", lambda n: (18, 20, 4))
    monkeypatch.setattr(pi_entry.shutil, "which", lambda x: "/usr/bin/node" if x == "node" else None)
    monkeypatch.setattr(pi_entry.pathlib.Path, "exists", lambda self: True)
    assert pi_entry.find_node() is None


def test_node_ok_when_new_enough(monkeypatch):
    monkeypatch.setattr(pi_entry, "_node_version", lambda n: (22, 23, 1))
    monkeypatch.setattr(pi_entry.shutil, "which", lambda x: "/usr/bin/node" if x == "node" else None)
    monkeypatch.setattr(pi_entry.pathlib.Path, "exists", lambda self: True)
    assert pi_entry.find_node() == "/usr/bin/node"


def test_probe_reports_missing_node(monkeypatch):
    monkeypatch.setattr(pi_entry, "find_node", lambda: None)
    ok, gap, pi = pi_entry.probe()
    assert ok is False and "node" in gap and pi is None


def test_probe_reports_missing_pi(monkeypatch):
    monkeypatch.setattr(pi_entry, "find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(pi_entry, "find_pi", lambda: None)
    ok, gap, pi = pi_entry.probe()
    assert ok is False and "pi" in gap.lower()


def test_probe_ok(monkeypatch):
    monkeypatch.setattr(pi_entry, "find_node", lambda: "/n/node")
    monkeypatch.setattr(pi_entry, "find_pi", lambda: "/p/pi")
    ok, node, pi = pi_entry.probe()
    assert ok is True and node == "/n/node" and pi == "/p/pi"
