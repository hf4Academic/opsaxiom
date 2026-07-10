"""Q-4 opsaxiom-attest + attestation schema 测试。"""
import pathlib, subprocess, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ABIN = ROOT / "tools" / "bin" / "opsaxiom-attest"
sys.path.insert(0, str(ROOT / "tools"))


def _run(*args):
    return subprocess.run([sys.executable, str(ABIN), *args], capture_output=True, text=True)


def test_attest_generates_valid_desensitized(tmp_path):
    adir = ROOT / "skills/host/load-high/attestations"
    try:
        r = _run("--skill", "host.cpu.load-high", "--skill-version", "0.1.0",
                 "--outcome", "resolved", "--mode", "navigator",
                 "--os-family", "rhel", "--os-version", "8.5.2", "--scale", "47",
                 "--rollback-exercised", "--attestor", "gh:t", "--date", "2026-01-01")
        assert r.returncode == 0
        files = list(adir.glob("*.yaml"))
        assert len(files) == 1
        import yaml
        att = yaml.safe_load(files[0].read_text())
        # 脱敏：精确版本被抹成分桶，精确规模被抹成区间
        assert att["env_fingerprint"]["os"]["version_bucket"] == "8.x"
        assert att["env_fingerprint"]["scale_bucket"] == "10-100 hosts"
        assert "8.5.2" not in files[0].read_text()   # 精确版本不得残留
        # 校验器接受
        import validate as V
        rep = V.validate_file(ROOT / "skills/host/load-high/skill.yaml", V._default_validator())
        assert not rep.errors
    finally:
        import shutil
        if adir.exists():
            shutil.rmtree(adir)


def test_attest_schema_rejects_pii_version(tmp_path):
    import json, yaml
    from jsonschema import Draft202012Validator
    schema = json.loads((ROOT / "schema/attestation.schema.json").read_text())
    v = Draft202012Validator(schema)
    bad = {"skill": "a.b.c", "skill_version": "0.1.0", "outcome": "resolved",
           "mode": "navigator",
           "env_fingerprint": {"os": {"family": "rhel", "version_bucket": "8.5.2"}},  # 精确版本=PII
           "rollback_exercised": False, "attestor": "x", "signature": "y"}
    assert list(v.iter_errors(bad)), "精确版本应被 schema 拒绝（只允许 N.x）"
