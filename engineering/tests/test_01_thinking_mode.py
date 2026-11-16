"""条目#1（工程验收表）Thinking Mode Activation。

原始要求（工程验收表）：
  thinking 字段：使用 anthropic style，在 request body 中加上
  {"thinking": {"type": "enabled"}}；默认开 thinking。
  Thinking Mode Activation: use the Anthropic style {"thinking": {"type": "enabled"}}.

补充要求（上线前条件第 2 条）：需要同时支持 thinking mode 和非 thinking mode，
通过 thinking.type = enabled/disabled 来控制，默认是 enabled；
官方不推荐使用 disabled，仅作为兼容性需求。
"""

from __future__ import annotations

# 需要一定推理量的题目
_REASONING_MSG = [{"role": "user", "content":
                   "鸡兔同笼，共有 35 个头，94 只脚。请计算鸡和兔各有多少只。"}]


def _req(model: str, thinking: dict | None, stream: bool = False, max_tokens: int = 8192) -> dict:
    req = {"model": model, "messages": _REASONING_MSG, "max_tokens": max_tokens}
    if thinking is not None:
        req["thinking"] = thinking
    if stream:
        req["stream"] = True
        req["stream_options"] = {"include_usage": True}
    return req


def test_01_enabled_returns_reasoning(client, rec):
    """thinking.type=enabled：响应应同时含 reasoning_content 与 content"""
    req = _req(client.model, {"type": "enabled"})
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("reasoning_content 非空", bool(result.reasoning_content.strip()),
               f"len={len(result.reasoning_content)}")
    rec.expect("content 非空", bool(result.content.strip()))


def test_01_disabled_no_reasoning(client, rec):
    """thinking.type=disabled：响应不应含 reasoning_content"""
    req = _req(client.model, {"type": "disabled"}, max_tokens=2048)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("reasoning_content 为空", not result.reasoning_content.strip(),
               f"len={len(result.reasoning_content)}")
    rec.expect("content 非空", bool(result.content.strip()))


def test_01_default_is_enabled(client, rec):
    """不传 thinking 字段时默认 enabled（应返回 reasoning_content）"""
    req = _req(client.model, None)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("默认返回 reasoning_content", bool(result.reasoning_content.strip()),
               f"len={len(result.reasoning_content)}")
    rec.expect("content 非空", bool(result.content.strip()))


def test_01_enabled_stream(client, rec):
    """流式 + enabled：应先出现 reasoning_content chunk，再出现 content chunk，finish=stop"""
    req = _req(client.model, {"type": "enabled"}, stream=True)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("流中含 reasoning_content", bool(result.reasoning_content.strip()),
               f"n_chunks={result.n_chunks}")
    rec.expect("流中含 content", bool(result.content.strip()))
    rec.expect("finish_reason == stop", result.finish_reason == "stop",
               f"finish_reason={result.finish_reason}")
    rec.expect("usage 非空（include_usage 生效）", bool(result.usage),
               f"usage={result.usage}")


def test_01_disabled_stream(client, rec):
    """流式 + disabled：不应出现 reasoning_content chunk"""
    req = _req(client.model, {"type": "disabled"}, stream=True, max_tokens=2048)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("流中无 reasoning_content", not result.reasoning_content.strip())
    rec.expect("流中含 content", bool(result.content.strip()))
