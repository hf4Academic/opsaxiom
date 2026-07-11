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


def add_diagnose(sub):
    dp = sub.add_parser("diagnose", help="按症状匹配 Skill")
    dp.add_argument("symptom")
    dp.add_argument("--top", type=int, default=5)
    dp.add_argument("--json", action="store_true", help="输出结构化 JSON 候选")
    dp.set_defaults(fn=cmd_diagnose)
