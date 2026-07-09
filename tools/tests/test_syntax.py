"""O-5 命令语法树测试：核心是证明能拦截 CLI 幻觉/跨平台混用。"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import syntax_check as SC  # noqa: E402


def _has_error(issues):
    return any(lvl == "ERROR" for lvl, _ in issues)


def test_legit_cisco_passes():
    assert SC.check_command("cisco_ios", "show ip bgp summary") == []
    assert SC.check_command("cisco_ios", "show ip bgp neighbors {{peer_ip}} | include prefixes") == []
    assert SC.check_command("cisco_ios", "clear ip bgp {{peer_ip}} soft") == []


def test_legit_huawei_passes():
    assert SC.check_command("huawei_vrp", "display bgp peer {{peer_ip}} verbose") == []
    assert SC.check_command("huawei_vrp", "reset bgp {{peer_ip}}") == []


def test_legit_junos_passes():
    assert SC.check_command("junos", "show bgp summary | match {{peer_ip}}") == []
    assert SC.check_command("junos", "clear bgp neighbor {{peer_ip}} soft") == []


def test_cross_platform_hallucination_caught():
    # 在思科设备上敲华为命令 —— 必须 ERROR
    assert _has_error(SC.check_command("cisco_ios", "display bgp peer {{peer_ip}}"))
    # 在华为设备上敲思科命令
    assert _has_error(SC.check_command("huawei_vrp", "show ip bgp summary"))
    # 在 junos 上敲思科 clear
    assert _has_error(SC.check_command("junos", "clear ip bgp {{peer_ip}}"))


def test_nonexistent_verb_caught():
    assert _has_error(SC.check_command("cisco_ios", "get bgp status"))
    assert _has_error(SC.check_command("cisco_ios", "show ip bgp-neighbors-all"))


def test_uncovered_platform_skipped():
    # linux/kubectl 无语法树 —— 跳过（不报错）
    assert SC.check_command("linux", "rm -rf /") == []
    assert SC.check_command("kubectl", "kubectl get pods") == []
