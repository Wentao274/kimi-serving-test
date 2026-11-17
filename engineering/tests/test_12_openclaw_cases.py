"""补充条目（上线前条件第 7 条）Tool call（OpenClaw）测试用例（12 条，附件回放）。

原始要求：供应商应该能处理 tool call 的测试用例。OpenClaw 是 tool call 的
一种特例，且比例较高。以下请求应该返回 finish_reason = 'tool_calls'。

数据源：engineering/data/9.openclaw_cases12.jsonl
  每行 {"line": N, "request": {...}}，为真实 OpenClaw 多轮 agent 轨迹
  （16-364 条消息，含 thinking/reasoning_content 历史、stream 配置等）。

全部用例期望 finish_reason == "tool_calls"，且 tool_calls 结构合法
（function.name 非空、arguments 为合法 JSON）。

回放对齐说明：官方用例 case12 原生 stream=false 却携带 stream_options，
官方平台容忍、严格网关按 OpenAI 规范返回 400；回放时与官方平台容忍度
对齐，stream=false 自动剥离 stream_options 并在用例记录中标注。
"""

from __future__ import annotations

import json

import pytest

from engineering.core.data import load_openclaw_cases

_CASES = load_openclaw_cases()
_IDS = [f"case{i:02d}" for i in range(1, len(_CASES) + 1)]


def _valid_tool_calls(tool_calls: list) -> tuple[bool, str]:
    if not tool_calls:
        return False, "tool_calls 为空"
    for tc in tool_calls:
        fn = (tc or {}).get("function") or {}
        if not fn.get("name"):
            return False, f"tool_call 缺少 function.name: {tc}"
        args = fn.get("arguments", "")
        if isinstance(args, str) and args:
            try:
                json.loads(args)
            except json.JSONDecodeError as exc:
                return False, f"arguments 非合法 JSON: {exc}"
    return True, ""


@pytest.mark.parametrize("case_idx", range(1, len(_CASES) + 1), ids=_IDS)
def test_12_openclaw_case(client, rec, settings, case_idx):
    """OpenClaw 用例回放：finish_reason == tool_calls"""
    row = _CASES[case_idx - 1]
    req = dict(row["request"])
    req["model"] = client.model
    n_msgs = len(req.get("messages", []))
    stream = bool(req.get("stream", False))

    # 与官方平台容忍度对齐：stream=false 时剥离 stream_options
    # （官方用例 case12 原生 stream=false 却带 stream_options；官方平台容忍，
    #   严格网关会按 OpenAI 规范返回 400。剥离不影响测试点本身）
    stripped = None
    if not stream and "stream_options" in req:
        stripped = req.pop("stream_options")

    rec.extra.update({
        "case_no": case_idx, "messages": n_msgs, "stream": stream,
        "n_tools": len(req.get("tools") or []),
        "thinking": req.get("thinking"),
    })
    if stripped is not None:
        rec.extra["stripped_stream_options"] = stripped
        rec.extra["note"] = "stream=false，已剥离原用例中的 stream_options（与官方平台容忍度对齐）"
    # 大 prompt（最多 400KB+）prefill 耗时较长，超时翻倍
    result = client.chat(req, timeout=settings.timeout * 2)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())

    rec.expect("HTTP 2xx", result.ok,
               f"status={result.status_code} err={result.error}")
    rec.expect("finish_reason == 'tool_calls'", result.finish_reason == "tool_calls",
               f"actual={result.finish_reason}")
    ok, msg = _valid_tool_calls(result.tool_calls)
    rec.expect("tool_calls 结构合法", ok, msg)
    rec.expect("usage 非空", bool(result.usage), f"usage={result.usage}")
