"""I-10 fork 派生 + 出门拦截对抗测试。"""
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import hubtool  # noqa: E402
import localskill  # noqa: E402

BASE = {
    "apiVersion": "skill/v0.1", "kind": "Diagnostic",
    "metadata": {"id": "middleware.es.disk-watermark", "name": "x", "version": "0.1.0",
                 "taxonomy": "middleware/es/disk-watermark", "maturity": "sim_verified"},
    "tree": {"entry": "a", "nodes": [{"id": "a", "type": "done", "summary": "s"}]},
}


def test_is_local():
    assert localskill.is_local({"id": "local.x"})
    assert localskill.is_local({"id": "x", "visibility": "local"})
    assert not localskill.is_local({"id": "middleware.x"})


def test_fork_creates_local_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    base_dir = tmp_path / "src"; base_dir.mkdir()
    bp = base_dir / "skill.yaml"
    bp.write_text(yaml.safe_dump(BASE, allow_unicode=True), encoding="utf-8")

    sf = localskill.fork(BASE, bp)
    forked = yaml.safe_load(sf.read_text(encoding="utf-8"))
    m = forked["metadata"]
    assert m["id"] == "local.middleware.es.disk-watermark"
    assert m["derived_from"] == "middleware.es.disk-watermark@0.1.0"
    assert m["visibility"] == "local"
    assert m["maturity"] == "draft"                # 徽章清零
    assert localskill.is_local(m)


def test_cannot_fork_a_local_skill():
    with pytest.raises(localskill.LocalSkillError):
        localskill.fork({"metadata": {"id": "local.x"}}, "x")


# ---- 出门拦截：双保险 ----

def test_hub_push_rejects_local(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    with pytest.raises(localskill.LocalSkillError):
        hubtool.hub_push("local.middleware.es.disk-watermark")


def test_build_registry_rejects_local_in_skills(tmp_path):
    """对抗：故意把 fork 拷进公共 skills/ 再 build → 必须当场被拒。"""
    skills = tmp_path / "skills" / "local.x" / "0.1.0"
    skills.mkdir(parents=True)
    local_skill = dict(BASE)
    local_skill["metadata"] = dict(BASE["metadata"],
                                   id="local.middleware.x", visibility="local")
    (skills / "skill.yaml").write_text(
        yaml.safe_dump(local_skill, allow_unicode=True), encoding="utf-8")
    with pytest.raises(localskill.LocalSkillError, match="个人层"):
        hubtool.build_registry(tmp_path / "skills", tmp_path / "out")


def test_build_registry_ok_without_local(tmp_path):
    skills = tmp_path / "skills" / "middleware.x" / "0.1.0"
    skills.mkdir(parents=True)
    (skills / "skill.yaml").write_text(
        yaml.safe_dump(BASE, allow_unicode=True), encoding="utf-8")
    n = hubtool.build_registry(tmp_path / "skills", tmp_path / "out")
    assert n == 1                                    # 正常库照常构建
