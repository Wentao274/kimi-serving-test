"""检查项#1 三协议与响应格式。

按交付范围逐一验证 Chat、Responses、Messages 的流式与非流式请求，核对响应
结构及角色、内容类型和终态：Chat 核 choices[].message；Responses 核 output[]；
Messages 核 content[]。不能混用协议包装；未开放协议记硬失败并注明
protocol_not_open_note，不以其他协议结果替代。
"""

from __future__ import annotations

from k31selfcheck.protocols import (
    ProtocolClient,
    messages_content_types,
    responses_output_types,
)
from k31selfcheck.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_SIMPLE_MESSAGES = [{"role": "user", "content": "用一句话介绍你自己。"}]


def test_k01_chat_nonstream(client, rec):
    """Chat 非流式：choices[].message 结构、角色与 finish_reason 终态"""
    req = {"model": client.model, "messages": _SIMPLE_MESSAGES, "max_completion_tokens": 2048}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("Chat 非流式 HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")

    body = r.response_json or {}
    choices = body.get("choices") or []
    rec.expect("响应含非空 choices[]", bool(choices), f"keys={list(body)}")
    msg = choices[0].get("message") or {}
    rec.expect("choices[0].message.role == assistant", msg.get("role") == "assistant",
               f"role={msg.get('role')!r}")
    rec.expect("choices[0].message.content 为非空字符串",
               isinstance(msg.get("content"), str) and bool(msg.get("content")),
               f"content[:80]={str(msg.get('content'))[:80]!r}")
    rec.expect("choices[0].finish_reason 非空（终态）",
               bool(choices[0].get("finish_reason")),
               f"finish_reason={choices[0].get('finish_reason')!r}")


def test_k01_chat_stream(client, rec):
    """Chat 流式：delta 分片、finish_reason 终态与 [DONE] 收尾"""
    req = {"model": client.model, "messages": _SIMPLE_MESSAGES,
           "max_completion_tokens": 2048, "stream": True}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("Chat 流式 HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.expect("收到 SSE 分片（n_chunks>0）", r.n_chunks > 0, f"n_chunks={r.n_chunks}")
    rec.expect("流以 [DONE] 收尾", "data: [DONE]" in r.raw_text,
               f"raw_tail={r.raw_text[-120:]!r}")
    rec.expect("重组后 content 非空", bool(r.content), f"content[:80]={r.content[:80]!r}")
    rec.expect("流式 finish_reason 非空（终态）", bool(r.finish_reason),
               f"finish_reason={r.finish_reason!r}")


def test_k01_responses_nonstream(proto, rec):
    """Responses 非流式：output[] 结构与终态；未开放记硬失败"""
    payload = {"input": "用一句话介绍你自己。", "max_output_tokens": 2048}
    r = proto.call_responses(payload)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses 非流式", r, "Responses /v1/responses")

    body = r.json_body or {}
    output = body.get("output") or []
    rec.expect("响应含非空 output[]", isinstance(output, list) and bool(output),
               f"keys={list(body)}")
    types = responses_output_types(r)
    rec.expect("output[] 含 message 类型项", "message" in types, f"output_types={types}")
    status = body.get("status")
    rec.expect("Responses 终态 status == completed", status == "completed",
               f"status={status!r}")


def test_k01_messages_nonstream(proto, rec):
    """Messages 非流式：content[] 结构；未开放记硬失败"""
    payload = {"messages": _SIMPLE_MESSAGES, "max_tokens": 2048}
    r = proto.call_messages(payload)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages 非流式", r, "Messages /anthropic/v1/messages")

    body = r.json_body or {}
    content = body.get("content") or []
    rec.expect("响应含非空 content[]", isinstance(content, list) and bool(content),
               f"keys={list(body)}")
    types = messages_content_types(r)
    rec.expect("content[] 含 text 类型块", "text" in types, f"content_types={types}")
    stop = body.get("stop_reason")
    rec.expect("Messages 终态 stop_reason 非空", bool(stop), f"stop_reason={stop!r}")
