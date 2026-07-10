"""V-1 doctor 自检测试。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import doctor  # noqa: E402


def test_doctor_passes_in_dev_env(capsys):
    # 开发环境必需项应全通过（pyyaml/jsonschema/cryptography 已装）
    rc = doctor.run()
    out = capsys.readouterr().out
    assert "OpsAxiom doctor" in out
    assert rc == 0                       # 无红项
    assert "Python ≥ 3.8" in out


def test_install_sh_exists_and_executable():
    p = ROOT / "install.sh"
    assert p.exists()
    import os
    assert os.access(p, os.X_OK)


def test_dockerfile_present():
    assert (ROOT / "Dockerfile").exists()
