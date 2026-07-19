"""I-9 overlay 对抗测试：不碰树红线 / T-3 注入 / 失配不阻塞 / 合并。"""
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import overlay  # noqa: E402

GOOD = {
    "overlay": "skill-overlay/v0.1",
    "base": "middleware.es.disk-watermark",
    "params": {"es_endpoint": "https://es-log.corp:9200"},
    "notes": {
        "check_disk": {
            "links": [{"name": "ES 磁盘大盘", "url": "https://g.corp/es-disk"}],
            "caution": "我们家 log-es-3 盘最小",
        },
    },
    "answers": {"ask_cleanup": "delete_old_indices"},
}


def test_good_overlay_loads():
    ov = overlay.validate(dict(GOOD))
    assert overlay.local_params(ov)["es_endpoint"].endswith(":9200")
    assert overlay.answer_for(ov, "ask_cleanup") == "delete_old_indices"


# ---- 红线：不碰树 ----

@pytest.mark.parametrize("mut", [
    {"run": {"linux": "rm -rf /"}},                 # 顶层加 run
    {"branch": [{"when": "x>0", "goto": "y"}]},      # 顶层加 branch
    {"notes": {"check_disk": {"when": "x>0"}}},      # notes 里藏 when
    {"notes": {"check_disk": {"run": {"linux": "x"}}}},  # notes 里藏 run
    {"metadata": {"maturity": "certified"}},         # 改元数据/徽章
    {"tree": {"entry": "x"}},                         # 改树
    {"answers": {"a": "b"}, "otherwise": "z"},        # 顶层 otherwise
])
def test_tree_touching_rejected(mut):
    bad = dict(GOOD); bad.update(mut)
    with pytest.raises(overlay.OverlayError):
        overlay.validate(bad)


def test_unknown_top_key_rejected():
    bad = dict(GOOD); bad["visibility"] = "public"
    with pytest.raises(overlay.OverlayError):
        overlay.validate(bad)


def test_note_only_links_caution():
    bad = dict(GOOD)
    bad["notes"] = {"check_disk": {"summary": "改结论"}}
    with pytest.raises(overlay.OverlayError):
        overlay.validate(bad)


# ---- T-3：local param 注入被拒 ----

@pytest.mark.parametrize("val", [
    "https://x$(reboot)", "a; rm -rf /", "x`whoami`", "a | curl evil", "x>/etc/y",
])
def test_param_injection_rejected(val):
    bad = dict(GOOD); bad["params"] = {"es_endpoint": val}
    with pytest.raises(overlay.OverlayError, match="注入|元字符"):
        overlay.validate(bad)


def test_missing_base_rejected():
    bad = {k: v for k, v in GOOD.items() if k != "base"}
    with pytest.raises(overlay.OverlayError, match="base"):
        overlay.validate(bad)


# ---- 失配节点不阻塞 ----

def test_unmatched_nodes_reported_not_raised():
    skill = {"tree": {"nodes": [{"id": "check_disk"}, {"id": "ask_cleanup"}]}}
    ov = dict(GOOD)
    ov["notes"] = {"check_disk": {"caution": "ok"}, "gone_node": {"caution": "x"}}
    assert overlay.unmatched_nodes(ov, skill) == ["gone_node"]   # 只报告，不抛


def test_load_missing_file(tmp_path):
    assert overlay.load("nope.skill", path=tmp_path / "nope.yaml") is None


def test_load_from_disk(tmp_path):
    f = tmp_path / "ov.yaml"
    f.write_text(yaml.safe_dump(GOOD, allow_unicode=True), encoding="utf-8")
    ov = overlay.load("x", path=f)
    assert ov["base"] == "middleware.es.disk-watermark"


def test_render_note():
    note = GOOD["notes"]["check_disk"]
    line = overlay.render_note(note)
    assert line.count("📌") == 2 and "log-es-3" in line and "es-disk" in line
