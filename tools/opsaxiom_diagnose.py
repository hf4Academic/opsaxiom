"""diagnose 子命令的 CLI 胶水（被 tools/bin/opsaxiom 动态加载）。"""
import json

import diagnose

_BADGE = {"draft": "⚪draft", "sim_verified": "🔵sim",
          "field_verified": "🟢field", "certified": "🟡cert"}


def diagnose_json(symptom, top=5):
    """结构化候选（X-1，供 webhook / 自动化消费）。"""
    hits = diagnose.match(symptom, top=top)
    return [{"id": sk["id"], "name": sk["name"], "maturity": sk["maturity"],
             "score": round(sc, 3), "symptom": sk.get("symptom", ""),
             "taxonomy": sk["taxonomy"]} for sc, sk in hits]


def cmd_diagnose(args):
    if getattr(args, "json", False):
        print(json.dumps(diagnose_json(args.symptom, top=args.top), ensure_ascii=False))
        return 0
    hits = diagnose.match(args.symptom, top=args.top)
    if not hits:
        print("没匹配到相关 Skill。可换个说法，或 `opsaxiom run <id>` 直接指定。")
        return 1
    print(f'症状「{args.symptom}」候选 Skill：')
    for i, (sc, sk) in enumerate(hits, 1):
        print(f"  {i}) [{_BADGE.get(sk['maturity'], sk['maturity'])}] {sk['id']}  —— {sk['name']}")
        if sk["symptom"]:
            print(f"       入口症状: {sk['symptom']}")
    print(f"\n用 `opsaxiom run {hits[0][1]['id']}` 开始排查（或选其它候选）。")
    return 0


def cmd_list(args):
    """列出本地 Skill（--json 供 pi 扩展选择器等程序化消费）。

    --recent：按文件修改时间新→旧排（发布选择器用：最近产生的排最前）；
    --drafts：把 skills-drafts/ 一并列出（maturity 标 draft，来源标 drafts）。
    """
    import pathlib
    import yaml
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    rows = []
    dirs = [("skills", ROOT / "skills")]
    if getattr(args, "drafts", False):
        dirs.append(("drafts", ROOT / "skills-drafts"))
    for src, base in dirs:
        if not base.is_dir():
            continue
        for p in base.rglob("skill.yaml"):
            try:
                m = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("metadata", {})
            except Exception:
                continue
            if not m.get("id"):
                continue
            rows.append({"id": m["id"], "name": m.get("name", ""),
                         "maturity": m.get("maturity", "draft"),
                         "l1": (m.get("taxonomy") or "?").split("/")[0],
                         "source": src, "mtime": int(p.stat().st_mtime),
                         "path": str(p.relative_to(ROOT))})
    if args.domain:
        rows = [s for s in rows if s["l1"] == args.domain]
    if getattr(args, "recent", False):
        rows.sort(key=lambda s: -s["mtime"])
    else:
        rows.sort(key=lambda s: s["id"])
    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    for s in rows:
        tag = "（草稿目录）" if s["source"] == "drafts" else ""
        print(f"[{_BADGE.get(s['maturity'], s['maturity'])}] {s['id']}  —— {s['name']}{tag}")
    return 0


def add_diagnose(sub):
    dp = sub.add_parser("diagnose", help="按症状匹配 Skill")
    dp.add_argument("symptom")
    dp.add_argument("--top", type=int, default=5)
    dp.add_argument("--json", action="store_true", help="输出结构化 JSON 候选")
    dp.set_defaults(fn=cmd_diagnose)
    lp = sub.add_parser("list", help="列出本地 Skill")
    lp.add_argument("domain", nargs="?", help="按域过滤（host/k8s/network/…）")
    lp.add_argument("--json", action="store_true")
    lp.add_argument("--recent", action="store_true", help="按最近修改排序")
    lp.add_argument("--drafts", action="store_true", help="包含 skills-drafts/")
    lp.set_defaults(fn=cmd_list)
