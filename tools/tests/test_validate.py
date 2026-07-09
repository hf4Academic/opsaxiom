"""
O-2 校验器测试。运行：cd tools && python -m pytest -q   （或仓库根 python -m pytest tools）
覆盖：exprlang（合法/非法各 ≥5）、语义规则 S1/S2/S4/S5/S7/S8、两个金标准零错误。
"""
import copy
import pathlib
import sys

import pytest
import yaml

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import exprlang            # noqa: E402
import validate as V      # noqa: E402


# ----------------------------------------------------------------------------
# exprlang：合法 / 非法各 ≥5
# ----------------------------------------------------------------------------
LEGAL = [
    "rows[0].pcent >= 90",
    "max(rows[].ipcent) > 90",
    "output.value > mount.size * 0.2",
    "count(rows[].path matches '/var/log') >= 1",
    "delta(input_errors, 60s) > 0",
    "state == 'Idle' and admin_state == 'shutdown'",
    "any(lines[] matches 'bad AS|OPEN.*error') or all(peers[].up)",
    "not (loss_pct == 100)",
]
ILLEGAL = [
    "os.system('rm -rf /')",       # 函数调用残留 → 多余 token
    "__import__('os')",            # 未知函数
    "rows[0].pcent >= 90 || true", # 非法字符
    "state = 'Idle'",              # 单等号
    "pcent > 90 evil",             # 多余 token
    "foo(x)",                      # 未知函数
    "",                            # 空
]


@pytest.mark.parametrize("e", LEGAL)
def test_expr_legal(e):
    ok, err = exprlang.validate_when(e)
    assert ok, f"应合法却被拒: {e} ({err})"


@pytest.mark.parametrize("e", ILLEGAL)
def test_expr_illegal(e):
    ok, _ = exprlang.validate_when(e)
    assert not ok, f"应非法却通过: {e}"


# ----------------------------------------------------------------------------
# 金标准：零 ERROR
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("p", sorted((ROOT / "skills").rglob("skill.yaml")))
def test_gold_standards_clean(p):
    rep = V.validate_file(p, V._default_validator())
    assert not rep.errors, f"{p} 有 ERROR: {rep.errors}"


# ----------------------------------------------------------------------------
# 语义规则：构造最小 skill，注入单点缺陷
# ----------------------------------------------------------------------------
def _minimal():
    return copy.deepcopy({
        "apiVersion": "skill/v0.1",
        "kind": "Diagnostic",
        "metadata": {
            "id": "test.min.case", "name": "t", "taxonomy": "test/min/case",
            "version": "0.1.0", "maturity": "draft",
            "platforms": [{"os": "linux"}],
            "provenance": {"generated_by": "test"},
        },
        "requirements": {"capability_level": "read", "connectors": ["ssh"]},
        "tree": {
            "entry": "c1",
            "nodes": [
                {"id": "c1", "type": "check",
                 "run": {"linux": "true"},
                 "branch": [{"when": "output.code == 0", "goto": "done1"}],
                 "otherwise": "escalate"},
                {"id": "done1", "type": "done", "summary": "ok"},
                {"id": "escalate", "type": "escalate", "summary": "esc"},
            ],
        },
    })


def _rules(rep):
    return {rule for level, rule, _msg in rep.items if level == V.ERROR}


def test_minimal_is_clean():
    rep = V.validate_skill(_minimal())
    assert not rep.errors, rep.items


def test_s5_bad_when():
    s = _minimal()
    s["tree"]["nodes"][0]["branch"][0]["when"] = "state = bad ||"
    assert "S5" in _rules(V.validate_skill(s))


def test_s4_missing_otherwise():
    s = _minimal()
    del s["tree"]["nodes"][0]["otherwise"]
    r = _rules(V.validate_skill(s))
    assert "S4" in r or "SCHEMA" in r   # schema 也要求 otherwise


def test_s7_dangling_goto():
    s = _minimal()
    s["tree"]["nodes"][0]["branch"][0]["goto"] = "nowhere"
    assert "S7" in _rules(V.validate_skill(s))


def test_s7_unreachable_node():
    s = _minimal()
    s["tree"]["nodes"].append({"id": "orphan", "type": "done", "summary": "x"})
    assert "S7" in _rules(V.validate_skill(s))


def _action_skill(risk="medium", with_preflight=True, with_rollback=True, with_verify=True):
    s = _minimal()
    act = {
        "id": "a1", "type": "action", "risk": risk,
        "run": {"linux": "touch /tmp/x"},
        "goto": "done1",
    }
    if with_rollback:
        act["rollback"] = {"type": "inverse", "run": {"linux": "rm /tmp/x"}}
    if with_verify:
        act["verify"] = {"run": {"linux": "test -f /tmp/x"}, "assert": "file_exists", "on_fail": "rollback"}
    if with_preflight:
        act["preflight"] = {
            "blast_radius": "仅 /tmp/x", "approval": "required",
            "watch": [{"run": {"linux": "ls /tmp/x"}, "expect": "存在"}],
            "abort_if": ["磁盘写满"],
        }
    s["tree"]["nodes"][0]["branch"][0]["goto"] = "a1"
    s["tree"]["nodes"].append(act)
    return s


def test_action_clean():
    assert not V.validate_skill(_action_skill()).errors


def test_s2_medium_risk_no_preflight():
    s = _action_skill(risk="high", with_preflight=False)
    assert "S2" in _rules(V.validate_skill(s))


def test_s1_rollback_platform_mismatch():
    s = _action_skill()
    # run 是 linux，rollback 换成 cisco_ios → S1 平台键不一致
    for n in s["tree"]["nodes"]:
        if n["id"] == "a1":
            n["rollback"]["run"] = {"cisco_ios": "no touch"}
    assert "S1" in _rules(V.validate_skill(s))


def test_s3_action_missing_verify():
    s = _action_skill(with_verify=False)
    r = _rules(V.validate_skill(s))
    assert "S3" in r or "SCHEMA" in r


def test_s8_maturity_requires_tests():
    s = _minimal()
    s["metadata"]["maturity"] = "sim_verified"   # 但无 tests
    assert "S8" in _rules(V.validate_skill(s))


# ---------------------------------------------------------------------------
# v0.2 新增规则
# ---------------------------------------------------------------------------
def test_s11_noop_rollback_rejected():
    s = _action_skill()
    for n in s["tree"]["nodes"]:
        if n["id"] == "a1":
            n["rollback"] = {"type": "inverse", "run": {"linux": "echo '仅提示，不可执行'"}}
    assert "S11" in _rules(V.validate_skill(s))


def test_s11_advisory_exempt_for_human_only():
    s = _action_skill()
    for n in s["tree"]["nodes"]:
        if n["id"] == "a1":
            n["human_only"] = True
            n["rollback"] = {"type": "inverse", "run": {"linux": "echo '人工指引'"}, "advisory": True}
    assert "S11" not in _rules(V.validate_skill(s))


def test_s11_advisory_without_human_only_rejected():
    s = _action_skill()
    for n in s["tree"]["nodes"]:
        if n["id"] == "a1":
            n["rollback"] = {"type": "inverse", "run": {"linux": "rm /tmp/x"}, "advisory": True}
    assert "S11" in _rules(V.validate_skill(s))


def test_s9_error_on_unsourced_template():
    s = _minimal()
    s["tree"]["nodes"][1]["summary"] = "值是 {{undeclared_var}}"
    assert "S9" in _rules(V.validate_skill(s))


def test_s9_ok_with_param():
    s = _minimal()
    s["metadata"]["params"] = [{"name": "mount", "source": "alert"}]
    s["tree"]["nodes"][1]["summary"] = "挂载点 {{mount}} 已处理"
    assert "S9" not in _rules(V.validate_skill(s))


def test_s9_ok_with_node_output_ref():
    s = _minimal()
    s["tree"]["nodes"][1]["summary"] = "最高 {{rows[0].pcent}}%"
    assert "S9" not in _rules(V.validate_skill(s))


def test_verify_assert_must_parse():
    s = _action_skill()
    for n in s["tree"]["nodes"]:
        if n["id"] == "a1":
            n["verify"]["assert"] = "服务正常"       # 散文，非表达式
    assert "S5" in _rules(V.validate_skill(s))
