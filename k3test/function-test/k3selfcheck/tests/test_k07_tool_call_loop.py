"""检查项#7 工具调用与多步闭环。

Chat 验证 tools[] + tool_choice=auto/required：finish_reason=tool_calls 且
tool_calls[].function.name/arguments 合法（arguments 为合法 JSON）；多步闭环——
第一轮拿 tool_call 后回填 role=tool 结果再请求，应返回正常最终回答。Responses
核 output[].type=function_call、Messages 核 content[].type=tool_use（协议开放时）。
"""

from __future__ import annotations

import json
import re

from k3selfcheck.protocols import (
    ProtocolClient,
    messages_content_types,
    responses_output_types,
)
from k3selfcheck.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_CHAT_TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市的实时天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名"}},
            "required": ["city"],
        },
    },
}]

_ASK = [{"role": "user", "content": "北京现在天气怎么样？"}]


def _check_tool_call(rec, r, source: str) -> dict | None:
    """核对 tool_calls 结构，返回第一个 tool_call（校验失败返回 None）。"""
    rec.expect(f"{source} finish_reason == tool_calls", r.finish_reason == "tool_calls",
               f"finish_reason={r.finish_reason!r}")
    rec.expect(f"{source} tool_calls 非空", bool(r.tool_calls), f"tool_calls={r.tool_calls}")
    if not r.tool_calls:
        return None
    tc = r.tool_calls[0]
    fn = tc.get("function") or {}
    rec.expect(f"{source} tool_calls[0].function.name 正确", fn.get("name") == "get_weather",
               f"name={fn.get('name')!r}")
    rec.expect(f"{source} tool_calls[0].id 非空（调用 ID）", bool(tc.get("id")),
               f"id={tc.get('id')!r}")
    args = fn.get("arguments")
    try:
        parsed = json.loads(args) if isinstance(args, str) else None
    except json.JSONDecodeError:
        parsed = None
    rec.expect(f"{source} arguments 为合法 JSON", parsed is not None,
               f"arguments={args!r}")
    if isinstance(parsed, dict):
        rec.expect(f"{source} arguments 含 city 参数", "city" in parsed,
                   f"parsed={parsed}")
    return tc


def test_k07_tool_choice_auto(client, rec):
    """Chat tools + tool_choice=auto：返回 tool_calls 且 name/arguments 合法"""
    req = {"model": client.model, "messages": _ASK, "tools": _CHAT_TOOLS,
           "tool_choice": "auto", "max_completion_tokens": 4096}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    _check_tool_call(rec, r, "auto")


def test_k07_tool_choice_required(client, rec):
    """Chat tool_choice=required：强制调用工具，返回 tool_calls"""
    req = {"model": client.model, "messages": _ASK, "tools": _CHAT_TOOLS,
           "tool_choice": "required", "max_completion_tokens": 4096}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.expect("required 强制调用：tool_calls 非空", bool(r.tool_calls),
               f"tool_calls={r.tool_calls} finish={r.finish_reason!r}")
    if r.tool_calls:
        fn = r.tool_calls[0].get("function") or {}
        rec.expect("required 调用 function.name 正确", fn.get("name") == "get_weather",
                   f"name={fn.get('name')!r}")
        args = fn.get("arguments")
        args_ok = True
        if isinstance(args, str):
            try:
                json.loads(args)
            except json.JSONDecodeError:
                args_ok = False
        rec.expect("required 调用 arguments 为合法 JSON", args_ok,
                   f"arguments={args!r}")
        leak = isinstance(args, str) and ("<:" in args or "|" in args)
        rec.expect("required 调用 arguments 无特殊 token 泄露", not leak,
                   f"arguments={args!r}")


def test_k07_multi_step_tool_loop(client, rec):
    """多步闭环：回填 role=tool 真实结果后，第二轮返回正常最终回答"""
    # 第一轮：拿 tool_call
    req1 = {"model": client.model, "messages": _ASK, "tools": _CHAT_TOOLS,
            "tool_choice": "auto", "max_completion_tokens": 4096}
    r1 = client.chat(req1)
    rec.attach_result(req1, r1, client.chat_completions_url, client.masked_headers())
    rec.expect("第一轮 HTTP 2xx", r1.ok, f"status={r1.status_code} err={r1.error}")
    tc = _check_tool_call(rec, r1, "第一轮")
    rec.expect("拿到 tool_call 以进行回填", tc is not None, "第一轮未返回 tool_call")

    # 第二轮：回填 assistant tool_calls + role=tool 结果
    messages = list(_ASK) + [
        {"role": "assistant", "content": r1.content or "", "tool_calls": r1.tool_calls},
        {"role": "tool", "tool_call_id": tc["id"], "content": "晴，气温 25℃，微风"},
    ]
    req2 = {"model": client.model, "messages": messages, "tools": _CHAT_TOOLS,
            "max_completion_tokens": 4096}
    r2 = client.chat(req2)
    rec.attach_result(req2, r2, client.chat_completions_url, client.masked_headers())
    rec.extra["multi_step"] = {"round1_finish": r1.finish_reason,
                               "round2_finish": r2.finish_reason,
                               "tool_call_id": tc["id"]}
    rec.expect("第二轮 HTTP 2xx", r2.ok, f"status={r2.status_code} err={r2.error}")
    rec.expect("第二轮返回正常最终回答（content 非空）", bool(r2.content),
               f"content[:120]={r2.content[:120]!r}")
    rec.expect("第二轮正常收尾（finish_reason=stop）", r2.finish_reason == "stop",
               f"finish_reason={r2.finish_reason!r}")


def test_k07_responses_function_call(proto, rec):
    """Responses tools：output[] 含 function_call 项且 name/arguments 合法；未开放记硬失败"""
    payload = {
        "input": _ASK[0]["content"],
        "max_output_tokens": 4096,
        "tools": [{
            "type": "function",
            "name": "get_weather",
            "description": "查询指定城市的实时天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }],
    }
    r = proto.call_responses(payload)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses 工具调用", r, "Responses /v1/responses")
    types = responses_output_types(r)
    rec.expect("output[] 含 function_call 类型项", "function_call" in types,
               f"output_types={types}")
    fc = next((i for i in (r.json_body or {}).get("output") or []
               if isinstance(i, dict) and i.get("type") == "function_call"), None)
    if fc is not None:
        rec.expect("function_call.name 正确", fc.get("name") == "get_weather",
                   f"name={fc.get('name')!r}")
        try:
            parsed = json.loads(fc.get("arguments") or "")
        except (json.JSONDecodeError, TypeError):
            parsed = None
        rec.expect("function_call.arguments 为合法 JSON", parsed is not None,
                   f"arguments={fc.get('arguments')!r}")
        rec.expect("function_call 含调用 ID（call_id/id）",
                   bool(fc.get("call_id") or fc.get("id")),
                   f"call_id={fc.get('call_id')!r} id={fc.get('id')!r}")


def test_k07_messages_tool_use(proto, rec):
    """Messages tools：content[] 含 tool_use 块且 name/input 合法；未开放记硬失败"""
    payload = {
        "messages": _ASK,
        "max_tokens": 4096,
        "tools": [{
            "name": "get_weather",
            "description": "查询指定城市的实时天气",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }],
    }
    r = proto.call_messages(payload)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages 工具调用", r, "Messages /anthropic/v1/messages")
    types = messages_content_types(r)
    rec.expect("content[] 含 tool_use 类型块", "tool_use" in types,
               f"content_types={types}")
    tu = next((c for c in (r.json_body or {}).get("content") or []
               if isinstance(c, dict) and c.get("type") == "tool_use"), None)
    if tu is not None:
        rec.expect("tool_use.name 正确", tu.get("name") == "get_weather",
                   f"name={tu.get('name')!r}")
        rec.expect("tool_use.input 为 object 且含 city",
                   isinstance(tu.get("input"), dict) and "city" in tu["input"],
                   f"input={tu.get('input')!r}")
        rec.expect("tool_use.id 非空（调用 ID）", bool(tu.get("id")), f"id={tu.get('id')!r}")
