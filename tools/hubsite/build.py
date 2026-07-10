"""
Hub 静态网站生成器（V-5，docs/08 §3.4）——registry → 纯静态 HTML。

无 JS 框架依赖：首页嵌入 index 数据 + 原生 JS 关键词过滤；每个 Skill 一张详情页
（决策树文本可视化、cautions、maturity 徽章、attestation 列表与验签状态）。
私有环境对内网 registry 跑一遍即得内部 Hub。

用法：python tools/hubsite/build.py <registry_dir> <out_dir>
"""
import html
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import yaml            # noqa: E402

BADGE = {"draft": ("⚪", "#9ca3af"), "sim_verified": ("🔵", "#3b82f6"),
         "field_verified": ("🟢", "#22c55e"), "certified": ("🟡", "#eab308")}

CSS = """
:root{--bg:#0b1020;--card:#161c2e;--fg:#e5e9f0;--mut:#94a3b8;--acc:#60a5fa}
*{box-sizing:border-box}body{margin:0;font:15px/1.6 -apple-system,Segoe UI,Roboto,'Noto Sans CJK SC',sans-serif;background:var(--bg);color:var(--fg)}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header{padding:24px 32px;border-bottom:1px solid #243}
h1{margin:0;font-size:22px}.sub{color:var(--mut);font-size:13px}
.wrap{max-width:1000px;margin:0 auto;padding:24px 32px}
input#q{width:100%;padding:12px 14px;border-radius:10px;border:1px solid #2a3550;background:#0f1526;color:var(--fg);font-size:15px;margin-bottom:20px}
.dom{color:var(--mut);text-transform:uppercase;font-size:12px;letter-spacing:.08em;margin:22px 0 8px}
.card{background:var(--card);border:1px solid #223;border-radius:12px;padding:14px 16px;margin:8px 0}
.card h3{margin:0 0 4px;font-size:16px}.badge{font-size:12px;padding:2px 8px;border-radius:999px;color:#000;font-weight:600}
.mut{color:var(--mut);font-size:13px}
.node{background:#0f1526;border-left:3px solid #2a3550;padding:8px 12px;margin:6px 0;border-radius:6px}
.node .t{font-weight:600}.caut{color:#fbbf24;font-size:13px;margin:3px 0 3px 12px}
.exit-done{border-left-color:#22c55e}.exit-esc{border-left-color:#f59e0b}
table{width:100%;border-collapse:collapse;margin-top:8px}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #223;font-size:13px}
.pill{font-size:12px;color:var(--mut)}
"""


def _esc(s):
    return html.escape(str(s or ""))


def _badge_html(m):
    icon, color = BADGE.get(m, ("?", "#888"))
    return f'<span class="badge" style="background:{color}">{icon} {_esc(m)}</span>'


def _tree_html(skill):
    out = []
    nodes = {n["id"]: n for n in skill.get("tree", {}).get("nodes", [])}
    entry = skill.get("tree", {}).get("entry")
    out.append(f'<p class="mut">入口：<code>{_esc(entry)}</code></p>')
    for n in skill.get("tree", {}).get("nodes", []):
        cls = "node"
        if n.get("type") == "done":
            cls += " exit-done"
        elif n.get("type") == "escalate":
            cls += " exit-esc"
        out.append(f'<div class="{cls}">')
        out.append(f'<div class="t">[{_esc(n.get("type"))}] {_esc(n.get("id"))} — {_esc(n.get("title") or n.get("summary",""))[:120]}</div>')
        for b in n.get("branch", []) or []:
            out.append(f'<div class="mut">· 当 <code>{_esc(b.get("when"))}</code> → {_esc(b.get("goto"))}</div>')
        if n.get("otherwise"):
            out.append(f'<div class="mut">· 否则 → {_esc(n["otherwise"])}</div>')
        for c in n.get("cautions", []) or []:
            out.append(f'<div class="caut">⚠ {_esc(c)}</div>')
        out.append('</div>')
    return "\n".join(out)


def _att_html(skill_dir):
    adir = skill_dir / "attestations"
    if not adir.is_dir():
        return '<p class="mut">暂无实地验证记录。</p>'
    rows = ['<table><tr><th>日期</th><th>结局</th><th>档位</th><th>环境</th><th>回滚</th><th>签名</th></tr>']
    for a in sorted(adir.glob("*.yaml")):
        att = yaml.safe_load(a.read_text(encoding="utf-8")) or {}
        env = att.get("env_fingerprint", {})
        os_ = env.get("os", {})
        sig = att.get("signature", "")
        sigshow = "✔ " + sig.split(":")[0] if sig and sig != "UNSIGNED-TODO" else "未签名"
        rows.append(f'<tr><td>{_esc(a.stem[:10])}</td><td>{_esc(att.get("outcome"))}</td>'
                    f'<td>{_esc(att.get("mode"))}</td>'
                    f'<td>{_esc(os_.get("family"))} {_esc(os_.get("version_bucket"))} / {_esc(env.get("scale_bucket"))}</td>'
                    f'<td>{"✔" if att.get("rollback_exercised") else "—"}</td><td class="pill">{_esc(sigshow)}</td></tr>')
    rows.append('</table>')
    return "\n".join(rows)


def _page(title, body):
    return (f'<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{_esc(title)}</title><style>{CSS}</style></head><body>{body}</body></html>')


def build_site(registry_dir, out_dir):
    reg = pathlib.Path(registry_dir)
    out = pathlib.Path(out_dir)
    (out / "skill").mkdir(parents=True, exist_ok=True)
    index = json.loads((reg / "index.json").read_text(encoding="utf-8"))

    # 详情页
    for e in index:
        sd = reg / "skills" / e["id"] / e["version"]
        skill = yaml.safe_load((sd / "skill.yaml").read_text(encoding="utf-8"))
        body = (f'<header><h1>{_esc(e["name"])} {_badge_html(e["maturity"])}</h1>'
                f'<div class="sub"><code>{_esc(e["id"])}</code> · {_esc(e["taxonomy"])} · v{_esc(e["version"])}'
                f' · <a href="../index.html">← 返回 Hub</a></div></header>'
                f'<div class="wrap"><h2>决策树</h2>{_tree_html(skill)}'
                f'<h2>实地验证（attestation）</h2>{_att_html(sd)}</div>')
        (out / "skill" / f"{e['id']}.html").write_text(_page(e["name"], body), encoding="utf-8")

    # 首页（域分组 + 客户端搜索）
    doms = {}
    for e in index:
        doms.setdefault(e["domain"], []).append(e)
    cards = []
    for dom in sorted(doms):
        cards.append(f'<div class="dom" data-dom="{_esc(dom)}">{_esc(dom)}（{len(doms[dom])}）</div>')
        for e in sorted(doms[dom], key=lambda x: x["id"]):
            hay = f'{e["id"]} {e["name"]} {e["taxonomy"]} {e.get("summary","")}'.lower()
            cards.append(
                f'<div class="card" data-hay="{_esc(hay)}">'
                f'<h3><a href="skill/{_esc(e["id"])}.html">{_esc(e["name"])}</a> {_badge_html(e["maturity"])}</h3>'
                f'<div class="mut"><code>{_esc(e["id"])}</code> · 实地记录 {e["attestations"]}</div>'
                f'<div class="mut">{_esc(e.get("summary",""))}</div></div>')
    js = ("<script>const q=document.getElementById('q');q.addEventListener('input',()=>{"
          "const v=q.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>{"
          "c.style.display=c.dataset.hay.includes(v)?'':'none';});"
          "document.querySelectorAll('.dom').forEach(d=>{let n=d.nextElementSibling,any=false;"
          "while(n&&n.classList.contains('card')){if(n.style.display!=='none')any=true;n=n.nextElementSibling;}"
          "d.style.display=any?'':'none';});});</script>")
    body = (f'<header><h1>OpsAxiom Skills Hub</h1>'
            f'<div class="sub">{len(index)} 个可信运维 Skill · 徽章表示成熟度 · 点开看决策树与实地验证</div></header>'
            f'<div class="wrap"><input id="q" placeholder="搜索症状 / id / 域…（如 磁盘、xid、暴破）">'
            f'{"".join(cards)}</div>{js}')
    (out / "index.html").write_text(_page("OpsAxiom Skills Hub", body), encoding="utf-8")
    return len(index)


def main():
    if len(sys.argv) != 3:
        print("用法：python tools/hubsite/build.py <registry_dir> <out_dir>", file=sys.stderr)
        return 2
    n = build_site(sys.argv[1], sys.argv[2])
    print(f"已生成静态站点：{sys.argv[2]}（{n} 个 Skill，首页 index.html）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
