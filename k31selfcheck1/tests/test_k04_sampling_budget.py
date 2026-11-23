"""检查项#4 采样与输出预算。

Chat 原厂 Pro 专属说明将 temperature=1.0、top_p=0.95、n=1、presence_penalty=0、
frequency_penalty=0 列为固定值，应被接受；max_completion_tokens 小值（64）精确
生效（completion≤64 且 finish=length）；Responses 用 max_output_tokens、Messages
用 max_tokens（协议开放时），不统一成 max_tokens。
"""

from __future__ import annotations

from k31selfcheck1.protocols import ProtocolClient
from k31selfcheck1.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_MESSAGES = [{"role": "user", "content": "写一段关于春天的描写，不少于 200 字。"}]
_BUDGET = 64


def test_k04_sampling_fixed_values_accepted(client, rec):
    """Chat 固定采样值 temperature=1.0/top_p=0.95/n=1/双 penalty=0 被接受"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 4096,
           "temperature": 1.0, "top_p": 0.95, "n": 1,
           "presence_penalty": 0, "frequency_penalty": 0}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("固定采样值组合被接受（HTTP 2xx）", r.ok,
               f"status={r.status_code} err={r.error}")
    choices = (r.response_json or {}).get("choices") or []
    rec.expect("n=1 时 choices 长度为 1", len(choices) == 1, f"len(choices)={len(choices)}")
    rec.expect("有最终回答", bool(r.content), f"content[:80]={r.content[:80]!r}")


def test_k04_chat_max_completion_tokens_budget(client, rec):
    """max_completion_tokens=64 精确生效：completion_tokens ≤ 64 且 finish_reason=length"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": _BUDGET}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    ct = (r.usage or {}).get("completion_tokens")
    rec.expect(f"completion_tokens ≤ {_BUDGET}（预算精确生效）",
               isinstance(ct, int) and ct <= _BUDGET, f"completion_tokens={ct!r}")
    rec.expect("预算耗尽时 finish_reason == length", r.finish_reason == "length",
               f"finish_reason={r.finish_reason!r}")
    rec.extra["note"] = ("常驻思考模型预算可能被思考耗尽导致正文为空，"
                         f"content 长度={len(r.content)} reasoning 长度={len(r.reasoning_content)}")


def test_k04_responses_max_output_tokens(proto, rec):
    """Responses：max_output_tokens=64 生效（output_tokens ≤ 64）；未开放记硬失败"""
    payload = {"input": "写一段关于春天的描写，不少于 200 字。",
               "max_output_tokens": _BUDGET}
    r = proto.call_responses(payload)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses max_output_tokens", r, "Responses /v1/responses")
    ot = (r.usage or {}).get("output_tokens")
    rec.expect(f"output_tokens ≤ {_BUDGET}（预算精确生效）",
               isinstance(ot, int) and ot <= _BUDGET, f"output_tokens={ot!r}")
    status = (r.json_body or {}).get("status")
    rec.check("预算耗尽终态为 incomplete/length 类（如实记录）",
              status in ("incomplete", "completed"),
              f"status={status!r}", soft=True)


def test_k04_messages_max_tokens(proto, rec):
    """Messages：max_tokens=64 生效（output_tokens ≤ 64）；未开放记硬失败"""
    payload = {"messages": _MESSAGES, "max_tokens": _BUDGET}
    r = proto.call_messages(payload)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages max_tokens", r, "Messages /anthropic/v1/messages")
    ot = (r.usage or {}).get("output_tokens")
    rec.expect(f"output_tokens ≤ {_BUDGET}（预算精确生效）",
               isinstance(ot, int) and ot <= _BUDGET, f"output_tokens={ot!r}")
    stop = (r.json_body or {}).get("stop_reason")
    rec.expect("预算耗尽时 stop_reason == max_tokens", stop == "max_tokens",
               f"stop_reason={stop!r}")
