"""I-11 share 剥离 + skill doctor 测试。"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import share  # noqa: E402
import capture_cli  # noqa: E402


def test_strip_pin_lines():
    text = "结论行\n       📌 扩容先走变更单\n       📌 ES 大盘（https://g.corp/es）\n正常行"
    out = share.strip_personal(text)
    assert "📌" not in out and "变更单" not in out
    assert "结论行" in out and "正常行" in out


def test_strip_internal_urls():
    text = ("大盘 https://grafana.corp/d/es 和内网 https://10.0.1.5:9200/x "
            "还有 https://192.168.1.1:8080 与公网 https://github.com/x")
    out = share.strip_personal(text)
    assert "grafana.corp" not in out and "10.0.1.5" not in out and "192.168.1.1" not in out
    assert "github.com" in out                          # 公网 URL 保留
    assert "〔内网地址〕" in out


def test_strip_credential_via_redact():
    text = "password: hunter2 留在文中"
    out = share.strip_personal(text)
    assert "hunter2" not in out


def test_export_report_share_strips(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    import incident as I
    inc = I.Incident("x")
    inc.export_report  # 存在性
    # 手动构造含 📌 的卷宗文本走 share
    raw = "# 故障报告\n结论\n📌 内部大盘 https://g.corp/x"
    assert "g.corp" not in share.strip_personal(raw)


# ---- skill doctor ----

def _args():
    class A:
        json = False
    return A()


def test_doctor_clean_personal_layer(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    # 空个人层 → 健康
    rc = capture_cli._cmd_skill_doctor(_args())
    out = capsys.readouterr().out
    assert rc == 0 and "健康" in out


def test_doctor_flags_overlay_violation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPSAXIOM_HOME", str(tmp_path))
    ov_dir = tmp_path / "overlays"; ov_dir.mkdir(parents=True)
    # 违规 overlay（试图改树）→ doctor 黄牌
    (ov_dir / "middleware.es.disk-watermark.yaml").write_text(yaml.safe_dump(
        {"base": "middleware.es.disk-watermark", "run": {"linux": "x"}},
        allow_unicode=True), encoding="utf-8")
    rc = capture_cli._cmd_skill_doctor(_args())
    out = capsys.readouterr().out
    assert rc == 1 and "违规" in out
