"""前置冒烟检查（非验收条目，仅用于测试前的基础设施 sanity check）。

- GET /models 可访问（OpenAI 协议兼容）
- 最小 chat/completions 请求成功且结构完整
- 错误 API key 被拒绝（401/403）
- 未知模型名被拒绝（4xx）
- 128 字符工具名可接受（协议兼容探针）
"""

from __future__ import annotations

import pytest


@pytest.mark.usefixtures("rec")
class TestSmokeConnectivity:
    def test_smoke_models_endpoint(self, client, rec):
        """GET /models 返回 200 且为 JSON 对象"""
        status, body, latency, error = client.get_models()
        rec.attach_raw("GET", client.models_url, client.masked_headers(), status, body, latency, error)
        rec.expect("GET /models 请求成功（无网络错误）", error is None, error or "")
        rec.expect("GET /models 返回 2xx", status is not None and 200 <= status < 300,
                   f"status={status}")
        import json
        try:
            data = json.loads(body)
            is_obj = isinstance(data, dict)
        except json.JSONDecodeError:
            is_obj = False
        rec.expect("响应为 JSON 对象", is_obj)

    def test_smoke_models_contains_model(self, client, rec):
        """模型列表中包含被测模型名（soft：部分网关不强制）"""
        import json
        status, body, latency, error = client.get_models()
        rec.attach_raw("GET", client.models_url, client.masked_headers(), status, body, latency, error)
        if not (status and 200 <= status < 300):
            rec.check("模型列表包含被测模型", False, f"/models 返回 {status}，无法校验", soft=True)
            pytest.skip("/models 不可用")
        try:
            data = json.loads(body)
            ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        except json.JSONDecodeError:
            ids = []
        rec.check(f"模型列表包含 '{client.model}'", client.model in ids,
                  f"列表={ids[:20]}", soft=True)

    def test_smoke_minimal_chat(self, client, rec):
        """最小 chat 请求返回 200，且 content/usage 结构完整"""
        req = {
            "model": client.model,
            "messages": [{"role": "user", "content": "Say OK and nothing else."}],
            "max_tokens": 32,
        }
        result = client.chat(req)
        rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
        rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
        rec.expect("content 非空", bool(result.content.strip()),
                   f"content={result.content[:80]!r}")
        rec.expect("usage 包含 prompt_tokens/completion_tokens",
                   "prompt_tokens" in result.usage and "completion_tokens" in result.usage,
                   f"usage={result.usage}")
        rec.expect("finish_reason 存在", result.finish_reason is not None,
                   f"finish_reason={result.finish_reason}")

    def test_smoke_invalid_key_rejected(self, client, settings, rec):
        """错误 API key 应返回 401/403"""
        from engineering.core.client import VendorClient
        bad = VendorClient(settings.base_url, "sk-invalid-key-0000000000",
                           settings.model, timeout=60.0)
        req = {
            "model": settings.model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 8,
        }
        result = bad.chat(req)
        rec.attach_result(req, result, bad.chat_completions_url, bad.masked_headers())
        rec.expect("返回 401/403", result.status_code in (401, 403),
                   f"status={result.status_code}")

    def test_smoke_unknown_model_rejected(self, client, rec):
        """未知模型名应返回 4xx"""
        req = {
            "model": "kst-definitely-not-exist-model-9z8x",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 8,
        }
        result = client.chat(req)
        rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
        rec.expect("返回 4xx", result.status_code is not None and 400 <= result.status_code < 500,
                   f"status={result.status_code}")

    def test_smoke_tool_name_128_chars(self, client, rec):
        """协议兼容探针：128 字符工具名应被接受且可调用"""
        name = "tool" + "a" * 124  # 恰好 128 字符
        req = {
            "model": client.model,
            "messages": [{"role": "user", "content": "what is the weather in beijing?"}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Get the weather of a city.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }],
            "tool_choice": "required",
        }
        result = client.chat(req)
        rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
        rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
        rec.expect("finish_reason == tool_calls", result.finish_reason == "tool_calls",
                   f"finish_reason={result.finish_reason}")
        rec.expect("返回的 tool_call 名称与 128 字符名一致",
                   bool(result.tool_calls) and result.tool_calls[0].get("function", {}).get("name") == name,
                   f"tool_calls={result.tool_calls[:1]}")
