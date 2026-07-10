"""diagnose 子命令的 CLI 胶水（被 tools/bin/opsaxiom 动态加载）。"""
import diagnose

_BADGE = {"draft": "⚪draft", "sim_verified": "🔵sim",
          "field_verified": "🟢field", "certified": "🟡cert"}


def cmd_diagnose(args):
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
    dp.set_defaults(fn=cmd_diagnose)
