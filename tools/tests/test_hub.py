"""V-4 Skills Hub 客户端测试（用仓库自身 skills/ 建演示 registry）。"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import hubtool  # noqa: E402


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path / "home"))
    reg = tmp_path / "registry"
    n = hubtool.build_registry(ROOT / "skills", reg)
    assert n > 0
    hubtool.hub_init(str(reg))
    return reg


def test_index_and_search(registry):
    idx = json.loads((registry / "index.json").read_text())
    assert any(e["id"] == "sec.access.bruteforce" for e in idx)
    hits = hubtool.hub_search("暴力破解")
    assert any(h["id"] == "sec.access.bruteforce" for h in hits)


def test_pull_sim_verified_passes_gates(registry):
    dst, rep = hubtool.hub_pull("sec.access.bruteforce")
    try:
        assert rep["validate_errors"] == 0
        assert (dst / "skill.yaml").exists()
        import yaml
        s = yaml.safe_load((dst / "skill.yaml").read_text())
        assert "origin" in s["metadata"]["provenance"]     # origin 标记
    finally:
        import shutil
        shutil.rmtree(dst, ignore_errors=True)


def test_pull_draft_rejected(registry):
    # 找一个 draft
    idx = json.loads((registry / "index.json").read_text())
    draft = next((e for e in idx if e["maturity"] == "draft"), None)
    if not draft:
        pytest.skip("无 draft 可测")
    with pytest.raises(PermissionError):
        hubtool.hub_pull(draft["id"])
    # --allow-draft 放开
    dst, _ = hubtool.hub_pull(draft["id"], allow_draft=True)
    import shutil
    shutil.rmtree(dst, ignore_errors=True)


def test_push_makes_bundle(registry, tmp_path):
    tar = hubtool.hub_push("sec.access.bruteforce", out_dir=tmp_path / "out")
    assert tar.exists() and tar.suffix == ".gz"
