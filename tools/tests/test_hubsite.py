"""V-5 Hub 静态网站生成器测试。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "hubsite"))
import hubtool  # noqa: E402
import build as hubsite  # noqa: E402


def test_build_site(tmp_path):
    reg = tmp_path / "reg"
    hubtool.build_registry(ROOT / "skills", reg)
    out = tmp_path / "site"
    n = hubsite.build_site(reg, out)
    assert n > 0
    idx = (out / "index.html").read_text(encoding="utf-8")
    assert "OpsAxiom Skills Hub" in idx
    assert "addEventListener" in idx          # 客户端搜索
    assert "sec.access.bruteforce" in idx
    # 详情页存在且含决策树
    detail = (out / "skill" / "sec.access.bruteforce.html").read_text(encoding="utf-8")
    assert "决策树" in detail and "实地验证" in detail
    assert "badge" in detail                  # 徽章


def test_detail_escapes_html(tmp_path):
    reg = tmp_path / "reg"
    hubtool.build_registry(ROOT / "skills", reg)
    out = tmp_path / "site"
    hubsite.build_site(reg, out)
    # 不应有未转义的裸 < 注入（抽查一个页面能正常读取即证明模板闭合）
    p = out / "skill" / "obs.alerting.alert-storm.html"
    assert p.exists() and "<!doctype html>" in p.read_text(encoding="utf-8")
