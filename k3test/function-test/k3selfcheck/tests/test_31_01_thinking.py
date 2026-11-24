"""3.1 Thinking控制：和官方模型对齐，按照要求通过指定参数来控制思考的开启和关闭。

kimi-k3.1-pro 官方规格：thinking.type=enabled/disabled 均须支持，不传 thinking 时
默认 enabled（disabled 仅作兼容）；thinking effort 支持 low / high / max 三档，
默认 max，通过 thinking.effort 传参。
"""

from __future__ import annotations

import pytest

from k3selfcheck.tests._common import expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "9.11 和 9.9 哪个大？简要回答。"}]
_EFFORTS = ["low", "high", "max"]


def test_31_01_thinking_enabled开启思考(client, rec):
    """Thinking控制：thinking.type=enabled 开启思考，响应应含 reasoning_content"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 4096,
           "thinking": {"type": "enabled"}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect("enabled 含 reasoning_content", bool(r.reasoning_content),
               f"reasoning_content 长度={len(r.reasoning_content or '')}")


def test_31_01_thinking_disabled关闭思考(client, rec):
    """Thinking控制：thinking.type=disabled 关闭思考，响应应不含 reasoning_content"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 4096,
           "thinking": {"type": "disabled"}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect("disabled 不含 reasoning_content", not r.reasoning_content,
               f"reasoning_content 长度={len(r.reasoning_content or '')}")


def test_31_01_不传thinking默认enabled(client, rec):
    """Thinking控制：不传 thinking 参数时默认开启（官方默认 enabled），响应应含 reasoning_content"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 4096}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect("不传 thinking 默认 enabled（含 reasoning_content）", bool(r.reasoning_content),
               f"reasoning_content 长度={len(r.reasoning_content or '')}")


@pytest.mark.parametrize("effort", _EFFORTS)
def test_31_01_thinking_effort官方三档(client, rec, effort):
    """Thinking控制：thinking.effort 官方三档 low/high/max 均应被接受且含 reasoning_content（默认 max）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 4096,
           "thinking": {"type": "enabled", "effort": effort}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect(f"effort={effort} 含 reasoning_content", bool(r.reasoning_content),
               f"reasoning_content 长度={len(r.reasoning_content or '')}")
