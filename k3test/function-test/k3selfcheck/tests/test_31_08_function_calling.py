"""3.1 Function Calling/工具调用：模型根据用户意图自动生成结构化函数调用请求。

覆盖：①tools 参数结构 + tool_choice=auto；②单轮多函数并行调用；③多轮上下文保持；
④函数调用结果回传后模型的二次推理能力（回答须引用工具结果要素）；
⑤是否兼容 OpenAI 的 Function Calling / Tool Use 协议格式（tool_choice=none/强制指定函数）。
"""

from __future__ import annotations

import json

from k3selfcheck.tests._common import (error_body, error_message, expect_4xx,
                                         expect_common_ok, send)

_TOOLS = [
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "查询指定城市的当前天气",
        "parameters": {"type": "object",
                        "properties": {"city": {"type": "string", "description": "城市名"}},
                        "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_current_time",
        "description": "查询指定城市的当前时间",
        "parameters": {"type": "object",
                        "properties": {"city": {"type": "string", "description": "城市名"}},
                        "required": ["city"]}}},
]


def _check_tool_calls_shape(rec, tool_calls, source: str) -> None:
    """硬校验 tool_calls 结构：id/type=function/function.name/arguments 为合法 JSON。"""
    rec.expect(f"{source} tool_calls 非空", bool(tool_calls), f"tool_calls={tool_calls}")
    for i, tc in enumerate(tool_calls or []):
        fn = (tc or {}).get("function") or {}
        rec.expect(f"{source} tool_calls[{i}] 结构合法（id/type=function/function.name）",
                   bool((tc or {}).get("id")) and (tc or {}).get("type") == "function"
                   and bool(fn.get("name")),
                   f"tc={tc}")
        args = fn.get("arguments")
        ok = True
        if isinstance(args, str):
            try:
                json.loads(args)
            except json.JSONDecodeError:
                ok = False
        rec.expect(f"{source} tool_calls[{i}].function.arguments 为合法 JSON", ok,
                   f"arguments={args!r}")


def test_31_08_工具调用auto模式(client, rec):
    """Function Calling/工具调用：①tools 定义 + tool_choice=auto → finish_reason=tool_calls 且结构合法"""
    req = {"model": client.model, "max_tokens": 2048, "tools": _TOOLS, "tool_choice": "auto",
           "messages": [{"role": "user", "content": "北京现在天气怎么样？"}]}
    r = send(client, rec, req)
    rec.expect("HTTP 200", r.ok and r.status_code == 200,
               f"status={r.status_code} err={r.error}")
    rec.expect("无报错/无超时", r.error is None, f"error={r.error!r}")
    rec.expect("finish_reason=tool_calls", r.finish_reason == "tool_calls",
               f"finish_reason={r.finish_reason!r}")
    _check_tool_calls_shape(rec, r.tool_calls, "auto")


def test_31_08_并行工具调用(client, rec):
    """Function Calling/工具调用：②并行调用——双工具提问应返回 ≥2 个 tool_calls"""
    req = {"model": client.model, "max_tokens": 2048, "tools": _TOOLS, "tool_choice": "auto",
           "messages": [{"role": "user", "content": "北京现在天气怎么样？现在几点了？"}]}
    r = send(client, rec, req)
    rec.expect("HTTP 200", r.ok and r.status_code == 200,
               f"status={r.status_code} err={r.error}")
    rec.expect("无报错/无超时", r.error is None, f"error={r.error!r}")
    names = sorted({(tc.get("function") or {}).get("name") for tc in r.tool_calls})
    rec.expect("并行调用返回 ≥2 个 tool_calls", len(r.tool_calls) >= 2,
               f"n_tool_calls={len(r.tool_calls)} names={names}")
    rec.check("并行调用覆盖两个工具（get_weather/get_current_time）",
              {"get_weather", "get_current_time"} <= set(names),
              f"names={names}", soft=True)
    _check_tool_calls_shape(rec, r.tool_calls, "parallel")


def test_31_08_多轮工具调用上下文(client, rec):
    """Function Calling/工具调用：③④多轮上下文保持 + 结果回传后二次推理（回答须引用工具结果要素）"""
    base_messages = [{"role": "user", "content": "北京现在天气怎么样？"}]
    req1 = {"model": client.model, "max_tokens": 2048, "tools": _TOOLS, "tool_choice": "auto",
            "messages": base_messages}
    r1 = client.chat(dict(req1))
    rec.expect("第一轮 HTTP 2xx 且返回 tool_calls", r1.ok and bool(r1.tool_calls),
               f"status={r1.status_code} err={r1.error} tool_calls={r1.tool_calls}")

    follow_messages = list(base_messages)
    follow_messages.append({"role": "assistant", "content": r1.content or None,
                            "tool_calls": r1.tool_calls})
    for tc in r1.tool_calls:
        follow_messages.append({
            "role": "tool", "tool_call_id": (tc or {}).get("id"),
            "content": json.dumps({"city": "北京", "weather": "晴", "temperature": "22°C"},
                                   ensure_ascii=False)})
    req2 = {"model": client.model, "max_tokens": 2048, "tools": _TOOLS, "tool_choice": "auto",
            "messages": follow_messages}
    r2 = send(client, rec, req2)
    expect_common_ok(rec, r2)
    rec.expect("回填 tool 结果后二次推理给出有效回答（非再次 tool_calls 空转）",
               bool(r2.content), f"content[:120]={(r2.content or '')[:120]!r}")
    rec.expect("二次推理回答引用工具结果要素（含 22°C/晴 等结果内容）",
               ("22" in (r2.content or "")) or ("晴" in (r2.content or "")),
               f"content[:200]={(r2.content or '')[:200]!r}")


def test_31_08_OpenAI协议格式兼容(client, rec):
    """Function Calling/工具调用：⑤OpenAI Tool Use 协议兼容——tool_choice=none 不触发调用；
    强制指定函数对象按官方契约为预期 4xx（不默认支持指定函数）"""
    # tool_choice=none：不得返回 tool_calls，走正常文本回答
    req_none = {"model": client.model, "max_tokens": 512, "tools": _TOOLS,
                "tool_choice": "none",
                "messages": [{"role": "user", "content": "北京现在天气怎么样？"}]}
    r1 = send(client, rec, req_none)
    expect_common_ok(rec, r1)
    rec.expect("tool_choice=none 不返回 tool_calls", not r1.tool_calls,
               f"tool_calls={r1.tool_calls}")
    rec.expect("tool_choice=none finish_reason=stop", r1.finish_reason == "stop",
               f"finish_reason={r1.finish_reason!r}")

    # 强制指定函数对象：官方契约为预期 4xx（不默认支持指定函数）
    req_forced = {"model": client.model, "max_tokens": 512, "tools": _TOOLS,
                  "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
                  "messages": [{"role": "user", "content": "随便聊聊。"}]}
    r2 = send(client, rec, req_forced)
    expect_4xx(rec, "强制指定函数对象（官方契约预期 4xx）", r2)
    rec.extra["forced_tool_choice_error"] = error_message(error_body(r2))[:200]
