"""N-4 OpenAI 兼容垫片测试：content parts 拍平 + 字段名映射（llama 模板兼容）。"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import llm_proxy  # noqa: E402


def test_flatten_content_parts():
    """pi-ai 发的多模态 content 数组 → 纯字符串（llama jinja 模板只认 str）。"""
    body = json.dumps({"messages": [
        {"role": "user", "content": [{"type": "text", "text": "你好"},
                                     {"type": "text", "text": "世界"}]}]}).encode()
    out = json.loads(llm_proxy.adapt_body(body))
    assert out["messages"][0]["content"] == "你好\n世界"


def test_max_completion_tokens_mapped():
    body = json.dumps({"messages": [], "max_completion_tokens": 128}).encode()
    out = json.loads(llm_proxy.adapt_body(body))
    assert out["max_tokens"] == 128 and "max_completion_tokens" not in out


def test_string_content_untouched():
    body = json.dumps({"messages": [{"role": "user", "content": "已经是字符串"}]}).encode()
    out = json.loads(llm_proxy.adapt_body(body))
    assert out["messages"][0]["content"] == "已经是字符串"


def test_non_json_passthrough():
    raw = b"not json at all"
    assert llm_proxy.adapt_body(raw) == raw


def test_existing_max_tokens_wins():
    body = json.dumps({"max_tokens": 50, "max_completion_tokens": 128}).encode()
    out = json.loads(llm_proxy.adapt_body(body))
    assert out["max_tokens"] == 50            # 已有 max_tokens 不覆盖
