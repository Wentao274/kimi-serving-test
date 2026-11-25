"""3.2 temperature：K3 规则——思考模式（含默认）仅允许 temperature=1.0；
关闭思考（disabled）模式仅允许 temperature=0.6；
显式传入其他值（thinking 下 0/0.6/0.3/2.0、disabled 下 0/1.0）返回 HTTP 400。

拒绝类断言只校验 4xx + 错误信息含 temperature 限制说明（兼容供应商/官方文案，
不校验具体错误码）。
"""

from __future__ import annotations

from k3selfcheck.tests._common import (error_body, error_message, expect_4xx,
                                        expect_common_ok, send)

_MESSAGES = [{"role": "user", "content": "用一句话介绍成都。"}]


def _expect_temp_reject(rec, name: str, r) -> None:
    """拒绝校验：4xx 且错误信息含 temperature 限制说明（兼容供应商/官方文案）。"""
    expect_4xx(rec, name, r)
    msg = error_message(error_body(r))
    ok = "temperature" in msg and "allowed" in msg
    rec.expect(f"{name} 错误信息含 temperature 限制说明（兼容供应商/官方文案）", ok,
               f"msg={msg[:200]!r}")


def test_32_09_thinking模式允许1_0(client, rec):
    """temperature：思考模式 temperature=1.0（唯一允许值）→ 2xx"""
    # max_tokens 需容纳 thinking 推理+正文
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "enabled"}, "temperature": 1.0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式拒绝0_6(client, rec):
    """temperature：思考模式 temperature=0.6（不允许，仅允许 1.0）→ 400（错误信息兼容）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0.6}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "思考模式 temperature=0.6", r)


def test_32_09_thinking模式拒绝0(client, rec):
    """temperature：思考模式 temperature=0（不允许，仅允许 1.0）→ 400（错误信息兼容）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "思考模式 temperature=0", r)


def test_32_09_disabled模式允许0_6(client, rec):
    """temperature：disabled 模式 temperature=0.6（唯一允许值）→ 2xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "disabled"}, "temperature": 0.6}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式拒绝0_3(client, rec):
    """temperature：思考模式 temperature=0.3（不允许）→ 400（错误信息兼容）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0.3}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "思考模式 temperature=0.3", r)


def test_32_09_thinking模式拒绝2_0(client, rec):
    """temperature：思考模式 temperature=2.0（不允许）→ 400（错误信息兼容）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 2.0}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "思考模式 temperature=2.0", r)


def test_32_09_disabled模式拒绝1_0(client, rec):
    """temperature：disabled 模式 temperature=1.0（不允许，仅允许 0.6）→ 400（错误信息兼容）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "disabled"}, "temperature": 1.0}
    r = send(client, rec, req)
    _expect_temp_reject(rec, "disabled 模式 temperature=1.0", r)


def test_32_09_disabled模式拒绝0(client, rec):
    """temperature：disabled 模式 temperature=0（不允许，仅允许 0.6）→ 400（错误信息兼容）"""
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
