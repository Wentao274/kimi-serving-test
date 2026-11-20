"""检查项#3 常驻思考与推理强度。

K3.1-Pro 原厂公开契约为始终开启思考：不传 thinking 参数时 Chat 响应应含
reasoning_content（硬）；thinking.type=enabled 应含；thinking.type=disabled 的
接受/拒绝行为如实记录（soft，不把 HTTP 200 写成开关生效）；reasoning_effort
low/high/max 三档应被接受（Chat）；Responses 用 reasoning.effort、Messages 用
output_config.effort（协议开放时）。任务应有有效最终回答，只有思考不代表完成。
"""

from __future__ import annotations

import pytest

from k31selfcheck.protocols import (
    ProtocolClient,
    messages_content_types,
    responses_output_types,
)
from k31selfcheck.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_MESSAGES = [{"role": "user", "content": "9.11 和 9.9 哪个大？简要回答。"}]


def test_k03_default_thinking_always_on(client, rec):
    """不传 thinking 参数：Chat 响应应含 reasoning_content（始终开启思考）且有最终回答"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 4096}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect("默认即含 reasoning_content（常驻思考）", bool(r.reasoning_content),
               f"reasoning_content 长度={len(r.reasoning_content or '')}")
    rec.expect("有有效最终回答（非仅思考）", bool(r.content),
               f"content[:80]={r.content[:80]!r}")


def test_k03_thinking_enabled(client, rec):
    """thinking.type=enabled：响应应含 reasoning_content 且有最终回答"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 4096,
           "thinking": {"type": "enabled"}}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect("enabled 时含 reasoning_content", bool(r.reasoning_content),
               f"reasoning_content 长度={len(r.reasoning_content or '')}")
    rec.expect("有有效最终回答（非仅思考）", bool(r.content),
               f"content[:80]={r.content[:80]!r}")


def test_k03_thinking_disabled_probe(client, rec):
    """thinking.type=disabled 探针（soft）：如实记录接受/拒绝，不把 200 写成开关生效"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 4096,
           "thinking": {"type": "disabled"}}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.extra["disabled_probe"] = {
        "status_code": r.status_code,
        "accepted": r.ok,
        "reasoning_chars": len(r.reasoning_content or ""),
    }
    if r.ok:
        rec.check("disabled 被接受（HTTP 200 仅表示参数被接受，不证明关闭生效）",
                  True, "供应商接受 thinking.type=disabled；"
                        f"响应 reasoning_content 长度={len(r.reasoning_content or '')}"
                        "（>0 说明思考实际未关闭）", soft=True)
        if r.reasoning_content:
            rec.check("disabled 下仍输出思考（与'关闭'语义不一致，如实记录）",
                      False, f"reasoning_content 长度={len(r.reasoning_content)}，"
                             "K3.1-Pro 为常驻思考模型，此结果符合原厂契约但需如实记录",
                      soft=True)
    else:
        rec.check("disabled 被拒绝（4xx 亦为合法行为，如实记录）",
                  400 <= (r.status_code or 0) < 500,
                  f"status={r.status_code} err={r.error}", soft=True)


@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_k03_reasoning_effort_accepted(client, rec, effort):
    """reasoning_effort=low/high/max 三档应被接受（Chat），且任务有最终回答"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 4096,
           "reasoning_effort": effort}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect(f"reasoning_effort={effort} 被接受（HTTP 2xx）", r.ok,
               f"status={r.status_code} err={r.error}")
    rec.expect("有有效最终回答（非仅思考）", bool(r.content),
               f"content[:80]={r.content[:80]!r}")


def test_k03_reasoning_effort_invalid(client, rec):
    """reasoning_effort 非法枚举探针（soft）：如实记录接受/拒绝"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 512,
           "reasoning_effort": "ultra"}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    if r.ok:
        rec.check("非法枚举 reasoning_effort=ultra 被拒绝（4xx）",
                  False, "供应商接受非法枚举值（HTTP 200 仅表示未校验，不证明生效）",
                  soft=True)
    else:
        rec.check("非法枚举 reasoning_effort=ultra 被拒绝（4xx）",
                  400 <= (r.status_code or 0) < 500,
                  f"status={r.status_code} err={r.error}", soft=True)


def test_k03_responses_reasoning_effort(proto, rec):
    """Responses：reasoning.effort 被接受且 output[] 含 reasoning 项；未开放记硬失败"""
    payload = {"input": "9.11 和 9.9 哪个大？简要回答。", "max_output_tokens": 4096,
               "reasoning": {"effort": "high"}}
    r = proto.call_responses(payload)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses reasoning.effort", r, "Responses /v1/responses")
    types = responses_output_types(r)
    rec.expect("output[] 含 reasoning 类型项（原生思考内容）", "reasoning" in types,
               f"output_types={types}")


def test_k03_messages_effort(proto, rec):
    """Messages：output_config.effort 被接受且 content[] 含 thinking 块；未开放记硬失败"""
    payload = {"messages": _MESSAGES, "max_tokens": 4096,
               "output_config": {"effort": "high"}}
    r = proto.call_messages(payload)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages output_config.effort", r, "Messages /anthropic/v1/messages")
    types = messages_content_types(r)
    rec.expect("content[] 含 thinking 类型块（原生思考内容）", "thinking" in types,
               f"content_types={types}")
