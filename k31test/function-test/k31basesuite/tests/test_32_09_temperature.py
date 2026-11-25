"""3.2 temperature：按官方口径断言——thinking 模式仅允许 1.0（固定）；
disabled 模式仅允许 0.6（固定）；显式传入其他值返回 HTTP 400。

说明：供应商网关规则 thinking 模式允许 {0, 0.6, 1.0}（与官方固定 1.0 不同）。
本模块按官方行为断言；供应商接受 0/0.6 时按"供应商网关设定规则"差异标注失败。
拒绝类断言只校验 4xx + 错误信息含 temperature 限制说明（兼容供应商/官方文案，
不校验具体错误码，官方返回 type=invalid_request_error 无 immutable_param）。
"""

from __future__ import annotations

from k31basesuite.tests._common import (error_body, error_message, expect_4xx,
                                         expect_common_ok, send)

_MESSAGES = [{"role": "user", "content": "用一句话介绍成都。"}]

_GATEWAY_NOTE = "thinking 模式允许 temperature=0/0.6 是供应商网关设定的规则（官方固定 1.0）"


def _expect_temp_reject(rec, name: str, r) -> None:
    """拒绝校验：4xx 且错误信息含 temperature 限制说明（兼容供应商/官方文案）。"""
    expect_4xx(rec, name, r)
    msg = error_message(error_body(r))
    ok = "temperature" in msg and "allowed" in msg
    rec.expect(f"{name} 错误信息含 temperature 限制说明（兼容供应商/官方文案）", ok,
               f"msg={msg[:200]!r}")


def _reject_with_gateway_note(rec, name: str, r) -> None:
    """官方口径应拒绝；若供应商网关规则放行（2xx），按差异标注失败。"""
    if r.ok:
        rec.expect(f"{name} 被供应商网关规则接受（官方固定 1.0，差异标注）", False,
                   f"{_GATEWAY_NOTE}，status={r.status_code}")
        return
    _expect_temp_reject(rec, name, r)


def test_32_09_thinking模式允许1_0(client, rec):
    """temperature：thinking 模式 temperature=1.0（官方唯一允许值）→ 2xx"""
    # max_tokens 需容纳 thinking 推理+正文
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "enabled"}, "temperature": 1.0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式官方口径拒绝0(client, rec):
    """temperature：官方口径 thinking 模式仅允许 1.0，temperature=0 → 400；
    供应商网关规则允许 0/0.6 时按差异标注失败"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0}
    r = send(client, rec, req)
    _reject_with_gateway_note(rec, "thinking 模式 temperature=0", r)


def test_32_09_thinking模式官方口径拒绝0_6(client, rec):
    """temperature：官方口径 thinking 模式仅允许 1.0，temperature=0.6 → 400；
    供应商网关规则允许 0/0.6 时按差异标注失败"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0.6}
    r = send(client, rec, req)
    _reject_with_gateway_note(rec, "thinking 模式 temperature=0.6", r)


def test_32_09_disabled模式允许0_6(client, rec):
    """temperature：disabled 模式 temperature=0.6（官方唯一允许值）→ 2xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "disabled"}, "temperature": 0.6}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式拒绝0_3(client, rec):
    """temperature：thinking 模式 temperature=0.3 → 400（错误信息兼容供应商/官方文案）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0.3}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "thinking 模式 temperature=0.3", r)


def test_32_09_thinking模式拒绝2_0(client, rec):
    """temperature：thinking 模式 temperature=2.0 → 400（错误信息兼容供应商/官方文案）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 2.0}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "thinking 模式 temperature=2.0", r)


def test_32_09_disabled模式拒绝1_0(client, rec):
    """temperature：disabled 模式 temperature=1.0 → 400（错误信息兼容供应商/官方文案）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "disabled"}, "temperature": 1.0}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "disabled 模式 temperature=1.0", r)


def test_32_09_disabled模式拒绝0(client, rec):
    """temperature：disabled 模式 temperature=0 → 400（错误信息兼容供应商/官方文案）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "disabled"}, "temperature": 0}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "disabled 模式 temperature=0", r)


def test_32_09_与top_p同时指定(client, rec):
    """temperature：与 top_p 同时指定（1.0/0.95 允许值）→ 2xx（互斥场景行为记录）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "temperature": 1.0, "top_p": 0.95}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.check("temperature 与 top_p 可同时指定（未观察到互斥拒绝）", True,
              "两个允许值同时指定被接受（2xx），行为已记录", soft=True)
