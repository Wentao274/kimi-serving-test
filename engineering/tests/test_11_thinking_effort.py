"""补充条目（上线前条件第 2 条 effort 部分）Thinking effort：low/high/max 三档，默认 max。

原始要求：在 thinking mode 下 thinking effort 支持 low, high, max 三档，默认 max。

实现要点：
- 三档均应被接受且返回 reasoning_content（硬校验）；
- 询问模型 "Which thinking_effort is the system invoked with?" 校验档位的方法
  依赖平台把 effort 注入 system prompt——仅官方平台可靠；第三方供应商
  system prompt 不含该信息，模型会一律按默认回答 max，不代表 effort 未生效。
  因此档位报告校验降为 soft，并以 reasoning 长度差异作为行为旁证；
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
    """询问模型生效档位（报告校验为 soft：仅官方平台可靠；硬校验为接受性+reasoning）"""
    req = _effort_req(client.model, effort, _ASK_MSG, max_tokens=2048)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.expect("reasoning_content 非空（effort 生效旁证）",
               bool(result.reasoning_content.strip()),
               f"len={len(result.reasoning_content)}")
    rec.extra["reasoning_length"] = len(result.reasoning_content)
    rec.check(f"模型报告的档位包含 '{effort}'（依赖平台 system prompt 注入，仅官方可靠）",
              effort in result.content.lower(),
              f"content={result.content[:200]!r}", soft=True)


def test_11_default_effort_is_max(client, rec):
    """不传 effort 时默认 max（报告校验为 soft）"""
    req = _effort_req(client.model, None, _ASK_MSG, max_tokens=2048)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    rec.check("模型报告的默认档位包含 'max'（依赖平台 system prompt 注入，仅官方可靠）",
              "max" in result.content.lower(),
              f"content={result.content[:200]!r}", soft=True)


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
