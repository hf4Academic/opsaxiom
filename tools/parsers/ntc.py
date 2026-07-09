"""
ntc-templates 包装器：网络设备 CLI 解析复用社区维护的 ntc-templates（TextFSM），
不重复造轮子。名字形如 ntc/<platform>/<command-slug>，如 ntc/cisco_ios/bgp-summary。

优雅降级：未安装 ntc-templates 时，make_parser 返回一个占位解析器，
返回 {"rows": [], "_unparsed": text, "_note": "ntc-templates 未安装"}，
校验器据此仅告警而不崩溃。国产设备（huawei_vrp/hp_comware）由 ntc-templates 覆盖，
未覆盖的板卡型号在 O 后续轮次补自研模板。
"""

_SLUG_TO_CMD = {
    "bgp-summary": "show ip bgp summary",
    "bgp-neighbor": "show ip bgp neighbors",
    "interface": "show interfaces",
}


def _available():
    try:
        import ntc_templates.parse  # noqa: F401
        return True
    except Exception:
        return False


def make_parser(name):
    # name = ntc/<platform>/<slug>
    _, platform, slug = name.split("/", 2)
    cmd = _SLUG_TO_CMD.get(slug, slug.replace("-", " "))

    def _parser(text):
        if not _available():
            return {"rows": [], "_unparsed": text, "_note": "ntc-templates 未安装(pip install ntc-templates)"}
        from ntc_templates.parse import parse_output
        try:
            rows = parse_output(platform=platform, command=cmd, data=text)
            return {"rows": rows}
        except Exception as e:  # 模板缺失等
            return {"rows": [], "_unparsed": text, "_note": f"ntc 解析失败: {e}"}

    return _parser
