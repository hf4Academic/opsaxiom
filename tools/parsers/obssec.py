"""
obs / sec 域解析器（U-3）。

数据源多为工具的 JSON 输出（amtool -o json、promtool、trivy -f json、
journalctl -o json 等）或结构化清单。统一 json.loads 后按契约挑标量；
缺字段留 None（决策树缺字段→None→不命中，安全），非 JSON→空结构走 otherwise。
派生标量（*_count / *_share / has_*）在这里算好，Skill 的 when 只比标量（B6）。
"""
import json


def _load(text):
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {"items": d} if isinstance(d, list) else {}
    except Exception:
        return {}


# ---- obs ----
def parse_alerts(text):
    d = _load(text)
    groups = d.get("groups") or {}
    top = max(groups.values()) if groups else 0
    active = d.get("active_alerts", sum(groups.values()) if groups else None)
    share = int(top * 100 / active) if active else None
    return {"active_alerts": active, "distinct_names": d.get("distinct_names", len(groups) or None),
            "top_group_count": top or None, "top_group_share": share}


def parse_alert_eval(text):
    d = _load(text)
    return {"firing": d.get("firing"), "metric_value": d.get("metric_value"),
            "threshold": d.get("threshold"), "flapping_count": d.get("flapping_count")}


def parse_metric_presence(text):
    d = _load(text)
    return {"series_count": d.get("series_count"), "last_scrape_age_s": d.get("last_scrape_age_s"),
            "target_up": d.get("target_up")}


def parse_target(text):
    d = _load(text)
    err = (d.get("last_error") or "").lower()
    return {"up": d.get("up"),
            "last_error_conn_refused": 1 if ("refused" in err or "connect" in err) else 0,
            "last_error_timeout": 1 if "timeout" in err else 0}


def parse_events(text):
    d = _load(text)
    return {"alert_events": d.get("alert_events"), "deploy_events": d.get("deploy_events"),
            "has_deploy_near_start": 1 if d.get("deploy_near_start") else 0}


# ---- sec ----
def parse_login(text):
    d = _load(text)
    return {"accepted_count": d.get("accepted_count"), "distinct_src_ips": d.get("distinct_src_ips"),
            "new_ip_count": d.get("new_ip_count"), "root_login_count": d.get("root_login_count"),
            "offhours_login_count": d.get("offhours_login_count")}


def parse_authfail(text):
    d = _load(text)
    return {"failed_count": d.get("failed_count"), "distinct_src_ips": d.get("distinct_src_ips"),
            "top_src_fail_count": d.get("top_src_fail_count"),
            "succeeded_after_fail": d.get("succeeded_after_fail")}


def parse_cert_inv(text):
    """证书清单：接受 JSON {certs:[{days_left}]} 或已聚合的标量。"""
    d = _load(text)
    if "certs" in d and isinstance(d["certs"], list):
        days = [c.get("days_left") for c in d["certs"] if c.get("days_left") is not None]
        return {"total_certs": len(d["certs"]),
                "min_days_left": min(days) if days else None,
                "expired_count": sum(1 for x in days if x < 0),
                "expiring_7d_count": sum(1 for x in days if 0 <= x < 7),
                "expiring_30d_count": sum(1 for x in days if 0 <= x < 30)}
    return {k: d.get(k) for k in ("total_certs", "min_days_left", "expired_count",
                                  "expiring_7d_count", "expiring_30d_count")}


def parse_vuln(text):
    d = _load(text)
    return {"critical_count": d.get("critical_count"), "high_count": d.get("high_count"),
            "has_fix_critical": 1 if d.get("fixable_critical") else 0,
            "kev_count": d.get("kev_count")}


def install(register):
    register("obs/alerts-v1", parse_alerts,
             {"scalars": ["active_alerts", "distinct_names", "top_group_count", "top_group_share"]})
    register("obs/alert-eval-v1", parse_alert_eval,
             {"scalars": ["firing", "metric_value", "threshold", "flapping_count"]})
    register("obs/metric-presence-v1", parse_metric_presence,
             {"scalars": ["series_count", "last_scrape_age_s", "target_up"]})
    register("obs/target-v1", parse_target,
             {"scalars": ["up", "last_error_conn_refused", "last_error_timeout"]})
    register("obs/events-v1", parse_events,
             {"scalars": ["alert_events", "deploy_events", "has_deploy_near_start"]})
    register("sec/login-v1", parse_login,
             {"scalars": ["accepted_count", "distinct_src_ips", "new_ip_count",
                          "root_login_count", "offhours_login_count"]})
    register("sec/authfail-v1", parse_authfail,
             {"scalars": ["failed_count", "distinct_src_ips", "top_src_fail_count",
                          "succeeded_after_fail"]})
    register("sec/cert-inv-v1", parse_cert_inv,
             {"scalars": ["total_certs", "min_days_left", "expired_count",
                          "expiring_7d_count", "expiring_30d_count"]})
    register("sec/vuln-v1", parse_vuln,
             {"scalars": ["critical_count", "high_count", "has_fix_critical", "kev_count"]})
