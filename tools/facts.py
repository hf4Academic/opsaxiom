"""
环境事实库 session MVP（Z-1，兑现 docs/01 §3 + docs/09 §2）。

一句话：把"只读命令的解析结果"变成可复用、可追溯、会过期的事实，
让 check 节点执行前先查库——命中就跳过（不再让人重贴一次 df），
并给诊断卷宗提供带出处的证据链（哪条命令、哪个字段、什么值、何时采的）。

设计（严格对齐 docs/09 §2）：
- fact = {key, value, source_cmd, target, ts, ttl, parser, field}
- key = 目标 + 归一化命令 + 解析器字段（field="*" 表示整份解析产物，供 check 复用）
- 解析器输出自动入库：一次命令 → 一个 "*" 整体事实 + 每个标量字段各一条事实
  （标量事实是卷宗的证据单元；"*" 事实是 check 复用的载体）。
- 故障态默认 TTL 300s；查库命中且未过期才复用，否则重新采集（诚实：宁可重采不给旧值）。

不做的（防镀金，本轮边界）：不做后台巡采（战时零探索留待事实库站稳后）；
不跨主机共享（target 隔离）；不落任何主机名/IP 之外的敏感串（值就是解析器产物，
R11 由上游脱敏层与解析器契约保证）。

时间可注入（now 参数）——测试用固定时钟，生产用 time.time()。
"""
import json
import pathlib
import re
import time

LOCAL = "local"                 # 默认目标：本机
DEFAULT_TTL = 300               # 故障态默认存活 5 分钟
_WS = re.compile(r"\s+")
BUNDLE = "*"                    # 整份解析产物的字段名


def normalize_cmd(cmd):
    """归一化命令：压平空白、去首尾。渲染后的命令（含 param）才入库，
    所以 `df -i  /data` 与 `df -i /data` 视作同一条。"""
    return _WS.sub(" ", (cmd or "").strip())


def make_key(target, cmd, field):
    return f"{target}\x1f{normalize_cmd(cmd)}\x1f{field}"


def _scalars(parsed):
    """从解析产物里挑出标量字段（排除 rows/lines/output 容器本身）。
    嵌套 output.* 里的标量也提出来——它们是分支判据的主力（§7.6c）。"""
    out = {}
    if not isinstance(parsed, dict):
        return out
    for k, v in parsed.items():
        if k in ("rows", "lines"):
            continue
        if k == "output" and isinstance(v, dict):
            for sk, sv in v.items():
                if isinstance(sv, (int, float, str, bool)):
                    out[sk] = sv
        elif isinstance(v, (int, float, str, bool)):
            out[k] = v
    return out


class FactStore:
    """session/incident 级事实库。内存为主，可 save/load 随审计归档。"""

    def __init__(self, default_ttl=DEFAULT_TTL):
        self._facts = {}            # key -> fact dict
        self.default_ttl = default_ttl

    # ---- 写 ----
    def put_parsed(self, cmd, parsed, target=LOCAL, parser=None,
                   now=None, ttl=None):
        """把一次命令的解析产物入库。

        写两类事实：
          · 一条 BUNDLE 事实（field="*"，value=整份 parsed）——供 check 节点复用；
          · 每个标量字段一条事实——供卷宗做证据引用。
        返回写入的标量字段名列表（便于调用方记日志）。
        """
        now = time.time() if now is None else now
        ttl = self.default_ttl if ttl is None else ttl
        ncmd = normalize_cmd(cmd)
        self._facts[make_key(target, ncmd, BUNDLE)] = {
            "key": make_key(target, ncmd, BUNDLE), "value": parsed,
            "source_cmd": ncmd, "target": target, "ts": now, "ttl": ttl,
            "parser": parser, "field": BUNDLE}
        written = []
        for field, val in _scalars(parsed).items():
            self._facts[make_key(target, ncmd, field)] = {
                "key": make_key(target, ncmd, field), "value": val,
                "source_cmd": ncmd, "target": target, "ts": now, "ttl": ttl,
                "parser": parser, "field": field}
            written.append(field)
        return written

    # ---- 读 ----
    def _live(self, fact, now):
        return fact is not None and (now - fact["ts"]) < fact["ttl"]

    def get_parsed(self, cmd, target=LOCAL, now=None):
        """查某命令的解析产物（BUNDLE 事实）。命中且未过期→返回 parsed，否则 None。
        这是 check 节点复用的入口：拿到就跳过执行/粘贴。"""
        now = time.time() if now is None else now
        f = self._facts.get(make_key(target, cmd, BUNDLE))
        return f["value"] if self._live(f, now) else None

    def get_field(self, field, cmd, target=LOCAL, now=None):
        now = time.time() if now is None else now
        f = self._facts.get(make_key(target, cmd, field))
        return f["value"] if self._live(f, now) else None

    def has(self, cmd, target=LOCAL, now=None):
        return self.get_parsed(cmd, target=target, now=now) is not None

    def evidence(self, now=None):
        """卷宗证据清单：所有存活的标量事实（排除 BUNDLE），按命令+字段稳定排序。
        每条是 {target, source_cmd, field, value, ts}——足够渲染"哪条命令→哪个字段=什么值"。"""
        now = time.time() if now is None else now
        rows = [f for f in self._facts.values()
                if f["field"] != BUNDLE and self._live(f, now)]
        rows.sort(key=lambda f: (f["target"], f["source_cmd"], f["field"]))
        return [{"target": f["target"], "source_cmd": f["source_cmd"],
                 "field": f["field"], "value": f["value"], "ts": f["ts"]}
                for f in rows]

    # ---- 持久化（随 incident 审计归档）----
    def save(self, path):
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps(list(self._facts.values()),
                                    ensure_ascii=False), encoding="utf-8")
        except TypeError:
            pass          # 极端情况下值不可序列化——跳过归档，不影响主流程
        return p

    def load(self, path, now=None):
        """从归档恢复；过期事实直接丢弃（恢复即体检，不把陈值带进新会话）。"""
        now = time.time() if now is None else now
        p = pathlib.Path(path)
        if not p.exists():
            return self
        for f in json.loads(p.read_text(encoding="utf-8")):
            if self._live(f, now):
                self._facts[f["key"]] = f
        return self
