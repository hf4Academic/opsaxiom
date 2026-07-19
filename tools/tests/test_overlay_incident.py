"""I-9 overlay ↔ incident 集成：本地参数并入假设、终点注记进卷宗。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "sim"))
import incident as I  # noqa: E402

SKILL_ID = "middleware.es.disk-watermark"


def _write_overlay(home):
    d = home / "overlays"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{SKILL_ID}.yaml").write_text(yaml.safe_dump({
        "overlay": "skill-overlay/v0.1",
        "base": SKILL_ID,
        "params": {"es_endpoint": "https://es-log.corp:9200"},
        "notes": {"done_disk_full": {
            "caution": "扩容要先走 CMDB 变更单",
            "links": [{"name": "ES 磁盘大盘", "url": "https://g.corp/es-disk"}],
        }},
    }, allow_unicode=True), encoding="utf-8")


def test_local_params_merged_and_note_in_dossier(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    _write_overlay(tmp_path)
    p, skill = I.load_skill_by_id(SKILL_ID)
    assert skill, "测试依赖真实库里的 es.disk-watermark"

    inc = I.Incident("ES 写不进去了")
    inc.add_hypotheses([skill])
    h = inc.hyps[0]
    # ① 本地参数并入了假设（source:local 占位符可被渲染）
    assert h.params.get("es_endpoint") == "https://es-log.corp:9200"
    assert h.overlay is not None

    # ② 终点注记进卷宗（模拟收敛到 done_disk_full）
    h.status, h.terminal = I.CONFIRMED, "done:done_disk_full"
    h.conclusion = "磁盘超水位锁写"
    text = inc.render_dossier()
    assert "📌 扩容要先走 CMDB 变更单" in text
    assert "ES 磁盘大盘" in text


def test_bad_overlay_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    d = tmp_path / "overlays"; d.mkdir(parents=True)
    # 违规 overlay（试图改树）——应被静默跳过，排查照常
    (d / f"{SKILL_ID}.yaml").write_text(yaml.safe_dump({
        "base": SKILL_ID, "run": {"linux": "rm -rf /"}}, allow_unicode=True),
        encoding="utf-8")
    _, skill = I.load_skill_by_id(SKILL_ID)
    inc = I.Incident("x")
    inc.add_hypotheses([skill])           # 不抛
    assert inc.hyps[0].overlay is None     # 违规 overlay 未加载
