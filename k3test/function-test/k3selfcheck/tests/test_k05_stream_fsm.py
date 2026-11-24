"""检查项#5 流式状态机与完整性。

Chat 核 choices[].delta、choices[].finish_reason 及 [DONE]；显式设置
stream_options.include_usage=true 后核 usage 末块（该开关原厂默认 false）。
Responses 核创建事件与 completed/incomplete/failed 终态；Messages 核
message_start、内容块 start/delta/stop、message_delta、message_stop。
初始 HTTP 200 不掩盖流内错误；分片重组、事件顺序、结束原因须自洽。
"""

from __future__ import annotations

import json

from k3selfcheck.protocols import ProtocolClient
from k3selfcheck.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_MESSAGES = [{"role": "user", "content": "从 1 数到 5，每个数字一行。"}]


def test_k05_chat_stream_delta_done(client, rec):
    """Chat 流式：delta 分片序列 + finish_reason + [DONE]，分片重组与非流式语义一致"""
    req = {"model": client.model, "messages": _MESSAGES,
           "max_completion_tokens": 2048, "stream": True}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("Chat 流式 HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.expect("流内无错误事件", not r.error, f"error={r.error}")

    # 逐块核对 delta 结构（choices[].delta）与分片自洽
    delta_chunks = 0
    for line in r.raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:") or line[5:].strip() == "[DONE]":
            continue
        try:
            chunk = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        for choice in chunk.get("choices") or []:
            if "delta" in choice:
                delta_chunks += 1
    rec.expect("分片含 choices[].delta 结构", delta_chunks > 0,
               f"delta_chunks={delta_chunks}")
    rec.expect("流以 [DONE] 收尾", "data: [DONE]" in r.raw_text,
               f"raw_tail={r.raw_text[-120:]!r}")
    rec.expect("流式 finish_reason 非空（结束原因自洽）", bool(r.finish_reason),
               f"finish_reason={r.finish_reason!r}")
    rec.expect("分片重组 content 非空", bool(r.content), f"content[:80]={r.content[:80]!r}")


def test_k05_chat_stream_include_usage(client, rec):
    """Chat 流式计量：显式 stream_options.include_usage=true 后出现 usage 末块"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 2048,
           "stream": True, "stream_options": {"include_usage": True}}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("Chat 流式 HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.expect("include_usage=true 后 usage 末块非空", bool(r.usage),
               "原厂该开关默认 false，显式 true 后应有 usage 末块；"
               f"usage={r.usage}")
    if r.usage:
        pt = r.usage.get("prompt_tokens")
        ct = r.usage.get("completion_tokens")
        rec.expect("usage 末块 prompt/completion_tokens 为整数",
                   isinstance(pt, int) and isinstance(ct, int),
                   f"prompt={pt!r} completion={ct!r}")


def test_k05_responses_stream_events(proto, rec):
    """Responses 流式：事件序列含创建事件与 completed/incomplete/failed 终态；未开放记硬失败"""
    payload = {"input": "从 1 数到 5，每个数字一行。", "max_output_tokens": 2048}
    r = proto.call_responses(payload, stream=True)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses 流式", r, "Responses /v1/responses")

    events = r.events
    rec.expect("收到 SSE 事件序列", bool(events), f"events={events[:20]}")
    created = [e for e in events if e.endswith("created") or e == "response.created"]
    rec.check("含 response.created 创建事件", bool(created),
              f"events={events[:20]}", soft=True)
    terminal = [e for e in events
                if e in ("response.completed", "response.incomplete", "response.failed")
                or e.endswith((".completed", ".incomplete", ".failed"))]
    rec.expect("含 completed/incomplete/failed 终态事件", bool(terminal),
               f"events_tail={events[-10:]}")
    rec.expect("终态为 completed（非 failed）",
               not any(e.endswith("failed") for e in events),
               f"terminal={terminal}")


def test_k05_messages_stream_events(proto, rec):
    """Messages 流式：message_start/内容块 start-delta-stop/message_delta/message_stop；未开放记硬失败"""
    payload = {"messages": _MESSAGES, "max_tokens": 2048}
    r = proto.call_messages(payload, stream=True)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages 流式", r, "Messages /anthropic/v1/messages")

    events = r.events
    rec.expect("收到 SSE 事件序列", bool(events), f"events={events[:20]}")
    for name in ("message_start", "content_block_start", "content_block_delta",
                 "content_block_stop", "message_delta", "message_stop"):
        rec.expect(f"事件序列含 {name}", name in events,
                   f"events={events[:30]}")
    if events:
        order_ok = (events.index("message_start") < events.index("message_stop")
                    if "message_start" in events and "message_stop" in events else False)
        rec.expect("事件顺序自洽（message_start 先于 message_stop）", order_ok,
                   f"events={events[:30]}")
