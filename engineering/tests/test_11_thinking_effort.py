"""补充条目（上线前条件第 2 条 effort 部分）Thinking effort：low/high/max 三档，默认 max。

原始要求：在 thinking mode 下 thinking effort 支持 low, high, max 三档，默认 max。

实现要点：
- 三档均应被接受且返回 reasoning_content；
- 直接询问模型 "Which thinking_effort is the system invoked with?"，
  模型从 system prompt 读取生效档位，比 reasoning 长度更可靠（硬校验）；
- 不传 effort 时默认 max（模型报告校验）；
- reasoning 长度排序（low < high < max）噪声大，仅作软性记录。
"""

from __future__ import annotations

import pytest

_EFFORTS = ("low", "high", "max")
_REASONING_MSG = [{"role": "user", "content":
                   "鸡兔同笼，共有 35 个头，94 只脚。请计算鸡和兔各有多少只。"}]
_ASK_MSG = [{"role": "user", "content":
             "Which thinking_effort is the system invoked with? (low/high/max)"}]


def _effort_req(model: str, effort: str | None, messages: list, max_tokens: int = 8192) -> dict:
    thinking: dict = {"type": "enabled", "keep": "all"}
    if effort is not None:
        thinking["effort"] = effort
    return {"model": model, "messages": messages, "max_tokens": max_tokens,
            "thinking": thinking}


@pytest.mark.parametrize("effort", _EFFORTS)
def test_11_effort_accepted(client, rec, effort):
    """thinking.effort 三档均应被接受，且返回 reasoning_content"""
    req = _effort_req(client.model, effort, _REASONING_MSG)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("reasoning_content 非空", bool(result.reasoning_content.strip()),
               f"len={len(result.reasoning_content)}")
    rec.extra["reasoning_length"] = len(result.reasoning_content)


@pytest.mark.parametrize("effort", _EFFORTS)
def test_11_effort_report(client, rec, effort):
    """询问模型生效档位，应答中应包含所设 effort"""
    req = _effort_req(client.model, effort, _ASK_MSG, max_tokens=2048)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect(f"模型报告的档位包含 '{effort}'", effort in result.content.lower(),
               f"content={result.content[:200]!r}")


def test_11_default_effort_is_max(client, rec):
    """不传 effort 时默认 max（模型报告应包含 'max'）"""
    req = _effort_req(client.model, None, _ASK_MSG, max_tokens=2048)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("模型报告的默认档位包含 'max'", "max" in result.content.lower(),
               f"content={result.content[:200]!r}")


def test_11_reasoning_length_order(client, rec):
    """reasoning 长度应大致 low < high < max（噪声大，soft 校验）"""
    lengths = {}
    for effort in _EFFORTS:
        req = _effort_req(client.model, effort, _REASONING_MSG)
        result = client.chat(req)
        if effort == "low":
            rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
        lengths[effort] = len(result.reasoning_content)
        rec.expect(f"effort={effort} HTTP 2xx", result.ok,
                   f"status={result.status_code} err={result.error}")
    rec.extra["reasoning_lengths"] = lengths
    ordered = lengths["low"] < lengths["high"] < lengths["max"]
    rec.check("reasoning 长度 low < high < max", ordered,
              f"low={lengths['low']}, high={lengths['high']}, max={lengths['max']}", soft=True)


def test_11_effort_stream(client, rec):
    """流式 + effort=high：reasoning 与 content chunk 均存在，finish=stop"""
    req = _effort_req(client.model, "high", _REASONING_MSG)
    req["stream"] = True
    req["stream_options"] = {"include_usage": True}
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("流中含 reasoning_content", bool(result.reasoning_content.strip()))
    rec.expect("流中含 content", bool(result.content.strip()))
    rec.expect("finish_reason == stop", result.finish_reason == "stop",
               f"finish_reason={result.finish_reason}")
