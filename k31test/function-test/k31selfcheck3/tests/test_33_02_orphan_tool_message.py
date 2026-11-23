"""孤儿 tool 消息校验：role=tool 消息必须引用前序 assistant tool_calls 中存在的
tool_call_id；孤儿（无匹配/无前置/重复回填）应被拒绝（4xx），合法回填应正常（2xx）。"""

from __future__ import annotations

import json

from k31basesuite.tests._common import (error_body, error_message, expect_4xx,
                                         expect_common_ok, send)

_TOOL_CALLS = [{"id": "call_1", "type": "function",
                "function": {"name": "get_weather", "arguments": "{\"city\": \"北京\"}"}}]


def _msgs_with_tool(tool_msgs: list[dict]) -> list[dict]:
    return [{"role": "user", "content": "北京现在天气怎么样？"},
            {"role": "assistant", "content": None, "tool_calls": _TOOL_CALLS},
            *tool_msgs]


def test_33_02_合法tool回填对照(client, rec):
    """孤儿 tool 消息校验：tool_call_id 匹配前序 tool_calls → 正常 2xx（对照组）"""
    req = {"model": client.model, "max_tokens": 512,
           "messages": _msgs_with_tool([
               {"role": "tool", "tool_call_id": "call_1",
                "content": json.dumps({"city": "北京", "weather": "晴"}, ensure_ascii=False)}])}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_33_02_tool_call_id无匹配拒绝(client, rec):
    """孤儿 tool 消息校验：tool_call_id 不存在于前序 tool_calls → 4xx"""
    req = {"model": client.model, "max_tokens": 16,
           "messages": _msgs_with_tool([
               {"role": "tool", "tool_call_id": "call_nonexistent_999",
                "content": "{\"weather\": \"晴\"}"}])}
    r = send(client, rec, req)
    expect_4xx(rec, "tool_call_id 无匹配（孤儿 tool 消息）", r)
    rec.extra["error_message"] = error_message(error_body(r))[:200]


def test_33_02_无前置tool_calls拒绝(client, rec):
    """孤儿 tool 消息校验：无任何前序 assistant tool_calls，直接出现 role=tool → 4xx"""
    req = {"model": client.model, "max_tokens": 16,
           "messages": [{"role": "user", "content": "你好"},
                        {"role": "tool", "tool_call_id": "call_1",
                         "content": "{\"weather\": \"晴\"}"}]}
    r = send(client, rec, req)
    expect_4xx(rec, "无前置 tool_calls 的 role=tool（孤儿 tool 消息）", r)
    rec.extra["error_message"] = error_message(error_body(r))[:200]


def test_33_02_重复回填同一id行为记录(client, rec):
    """孤儿 tool 消息校验：同一 tool_call_id 重复回填两次 → 期望 4xx（按实际行为记录）"""
    req = {"model": client.model, "max_tokens": 16,
           "messages": _msgs_with_tool([
               {"role": "tool", "tool_call_id": "call_1", "content": "{\"weather\": \"晴\"}"},
               {"role": "tool", "tool_call_id": "call_1", "content": "{\"weather\": \"雨\"}"}])}
    r = send(client, rec, req)
    if r.ok:
        expect_common_ok(rec, r)
        rec.check("重复回填同一 tool_call_id 被拒绝（4xx）", False,
                  "实际行为：接受（2xx），如实记录", soft=True)
    else:
        rec.check("重复回填同一 tool_call_id 被拒绝（4xx）", True,
                  f"status={r.status_code} msg={error_message(error_body(r))[:150]!r}",
                  soft=True)
