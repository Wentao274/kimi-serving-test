"""检查项#2 usage 与缓存计量。

Chat 核 usage.prompt_tokens/completion_tokens/total_tokens 及
usage.prompt_tokens_details.cached_tokens；Responses 核
usage.input_tokens/output_tokens/total_tokens；Messages 核
usage.input_tokens/output_tokens（及 cache_read_input_tokens/
cache_creation_input_tokens 若返回）。字段存在性 + 整数类型；缺失与 0 分开记录。
"""

from __future__ import annotations

from k31selfcheck1.protocols import ProtocolClient
from k31selfcheck1.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_MESSAGES = [{"role": "user", "content": "你好，请回复一个字。"}]


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def test_k02_chat_usage(client, rec):
    """Chat usage：prompt/completion/total 为整数；cached_tokens 缺失与 0 分开记录"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 1024}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("Chat HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")

    usage = r.usage or {}
    rec.expect("usage 非空", bool(usage), f"usage={usage}")
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        rec.expect(f"usage.{field} 为整数", _is_int(usage.get(field)),
                   f"{field}={usage.get(field)!r}")
    if _is_int(usage.get("prompt_tokens")) and _is_int(usage.get("completion_tokens")) \
            and _is_int(usage.get("total_tokens")):
        rec.expect("total_tokens == prompt + completion",
                   usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"],
                   f"total={usage['total_tokens']} prompt={usage['prompt_tokens']} "
                   f"completion={usage['completion_tokens']}")

    details = usage.get("prompt_tokens_details")
    if details is None:
        rec.check("usage.prompt_tokens_details.cached_tokens 存在",
                  False, "prompt_tokens_details 缺失（缺失与 0 需分开记录）", soft=True)
    else:
        cached = details.get("cached_tokens")
        rec.check("usage.prompt_tokens_details.cached_tokens 为整数（0 表示未命中，合法）",
                  _is_int(cached), f"cached_tokens={cached!r}", soft=True)


def test_k02_responses_usage(proto, rec):
    """Responses usage：input_tokens/output_tokens/total_tokens 为整数；未开放记硬失败"""
    payload = {"input": "你好，请回复一个字。", "max_output_tokens": 1024}
    r = proto.call_responses(payload)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses usage", r, "Responses /v1/responses")

    usage = (r.json_body or {}).get("usage") or {}
    rec.expect("usage 非空", bool(usage), f"usage={usage}")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        rec.expect(f"usage.{field} 为整数", _is_int(usage.get(field)),
                   f"{field}={usage.get(field)!r}")
    if _is_int(usage.get("input_tokens")) and _is_int(usage.get("output_tokens")) \
            and _is_int(usage.get("total_tokens")):
        rec.expect("total_tokens == input + output",
                   usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"],
                   f"total={usage['total_tokens']} input={usage['input_tokens']} "
                   f"output={usage['output_tokens']}")
    in_details = usage.get("input_tokens_details")
    if in_details is not None:
        rec.check("usage.input_tokens_details.cached_tokens 为整数（若返回）",
                  _is_int(in_details.get("cached_tokens")),
                  f"cached_tokens={in_details.get('cached_tokens')!r}", soft=True)


def test_k02_messages_usage(proto, rec):
    """Messages usage：input_tokens/output_tokens 为整数；缓存字段若返回则核整数"""
    payload = {"messages": _MESSAGES, "max_tokens": 1024}
    r = proto.call_messages(payload)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages usage", r, "Messages /anthropic/v1/messages")

    usage = (r.json_body or {}).get("usage") or {}
    rec.expect("usage 非空", bool(usage), f"usage={usage}")
    for field in ("input_tokens", "output_tokens"):
        rec.expect(f"usage.{field} 为整数", _is_int(usage.get(field)),
                   f"{field}={usage.get(field)!r}")
    for field in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        if field in usage:
            rec.check(f"usage.{field} 为整数（若返回；0 与缺失分开记录）",
                      _is_int(usage.get(field)), f"{field}={usage.get(field)!r}", soft=True)
        else:
            rec.extra.setdefault("messages_usage_missing", []).append(field)
