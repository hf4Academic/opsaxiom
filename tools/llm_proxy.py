"""
OpenAI 兼容垫片代理（N-4 补丁）——立在 pi 与 llama_cpp.server 之间。

现实问题（真机实锤）：pi-ai 按 OpenAI 规范发多模态 content parts
（[{type:'text',text:...}]），llama_cpp.server 的 jinja 模板只认字符串，
直接 500。垫片做三件确定性小事后原样转发（含 SSE 流式透传）：
  1. messages[].content 数组 → 拼接为纯文本字符串；
  2. max_completion_tokens → max_tokens（旧字段名）；
  3. 其余字节不动。

stdlib 实现（http.server + http.client），无新依赖，气隙可用。
"""
import http.client
import http.server
import json
import threading


def _flatten_content(c):
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts)
    return c


def adapt_body(raw):
    """转换请求体：content 拍平 + max_tokens 字段名。非 JSON 原样返回。"""
    try:
        body = json.loads(raw)
    except Exception:
        return raw
    for m in body.get("messages", []) or []:
        if "content" in m:
            m["content"] = _flatten_content(m["content"])
    if "max_completion_tokens" in body and "max_tokens" not in body:
        body["max_tokens"] = body.pop("max_completion_tokens")
    return json.dumps(body).encode("utf-8")


class _Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 必须显式声明：默认 1.0 下回 chunked 流式是非法组合，
    # openai 客户端会直接判连接错误（真机实锤）。
    protocol_version = "HTTP/1.1"
    upstream = ("127.0.0.1", 11436)

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        if method == "POST" and self.path.endswith("/chat/completions"):
            raw = adapt_body(raw)
        conn = http.client.HTTPConnection(*self.upstream, timeout=300)
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length")}
        headers["Content-Length"] = str(len(raw))
        conn.request(method, self.path, body=raw or None, headers=headers)
        resp = conn.getresponse()
        self.send_response(resp.status)
        hop = {"transfer-encoding", "connection", "keep-alive"}
        chunked = resp.getheader("Transfer-Encoding", "").lower() == "chunked"
        for k, v in resp.getheaders():
            if k.lower() not in hop:
                self.send_header(k, v)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        # 流式透传（SSE 逐块转发；chunked 需按协议回写）
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            if chunked:
                self.wfile.write(f"{len(chunk):x}\r\n".encode())
                self.wfile.write(chunk)
                self.wfile.write(b"\r\n")
            else:
                self.wfile.write(chunk)
            self.wfile.flush()
        if chunked:
            self.wfile.write(b"0\r\n\r\n")
        conn.close()

    def do_POST(self):
        try:
            self._proxy("POST")
        except Exception as e:                                     # noqa: BLE001
            try:
                self.send_error(502, str(e)[:100])
            except Exception:
                pass

    def do_GET(self):
        try:
            self._proxy("GET")
        except Exception as e:                                     # noqa: BLE001
            try:
                self.send_error(502, str(e)[:100])
            except Exception:
                pass

    def log_message(self, *a):                                     # 静默
        pass


def serve(listen_port=11435, upstream_port=11436, background=False):
    _Handler.upstream = ("127.0.0.1", upstream_port)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", listen_port), _Handler)
    if background:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        return httpd
    httpd.serve_forever()
