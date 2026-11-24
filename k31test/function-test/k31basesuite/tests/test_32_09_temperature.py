"""3.2 temperature：kimi-k3.1 网络层规则——thinking 模式允许 {0, 0.6, 1.0}；
关闭思考（disabled）模式只允许 {0.6}；显式传入不允许的值返回 HTTP 400 / immutable_param。
"""

from __future__ import annotations

from k31basesuite.tests._common import (error_body, error_message, expect_4xx,
                                          expect_common_ok, send)

_MESSAGES = [{"role": "user", "content": "用一句话介绍成都。"}]


def _expect_immutable_param(rec, name: str, r) -> None:
    """硬校验：4xx 且错误码为 immutable_param。"""
    expect_4xx(rec, name, r)
    body = error_body(r)
    code = ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "")
        code = code or str(body.get("code") or "")
    hint = code + " " + error_message(body)
    rec.expect(f"{name} 错误码 immutable_param", "immutable_param" in hint,
               f"code={code!r} body={str(body)[:200]!r}")


def test_32_09_thinking模式允许1_0(client, rec):
    """temperature：thinking 模式 temperature=1.0（允许值）→ 2xx"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "enabled"}, "temperature": 1.0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式允许0_6(client, rec):
    """temperature：thinking 模式 temperature=0.6（允许值）→ 2xx"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "enabled"}, "temperature": 0.6}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式允许0(client, rec):
    """temperature：thinking 模式 temperature=0（允许值）→ 2xx"""
    # max_tokens 需容纳 thinking 推理+正文
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "thinking": {"type": "enabled"}, "temperature": 0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_disabled模式允许0_6(client, rec):
    """temperature：disabled 模式 temperature=0.6（允许值）→ 2xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 256,
           "thinking": {"type": "disabled"}, "temperature": 0.6}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_09_thinking模式拒绝0_3(client, rec):
    """temperature：thinking 模式 temperature=0.3（不允许）→ 400 / immutable_param"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 0.3}
    r = send(client, rec, req)
    _expect_immutable_param(rec, "thinking 模式 temperature=0.3", r)


def test_32_09_thinking模式拒绝2_0(client, rec):
    """temperature：thinking 模式 temperature=2.0（不允许）→ 400 / immutable_param"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "enabled"}, "temperature": 2.0}
    r = send(client, rec, req)
    _expect_immutable_param(rec, "thinking 模式 temperature=2.0", r)


def test_32_09_disabled模式拒绝1_0(client, rec):
    """temperature：disabled 模式 temperature=1.0（不允许，仅允许 0.6）→ 400 / immutable_param"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "disabled"}, "temperature": 1.0}
    r = send(client, rec, req)
    _expect_immutable_param(rec, "disabled 模式 temperature=1.0", r)


def test_32_09_disabled模式拒绝0(client, rec):
    """temperature：disabled 模式 temperature=0（不允许，仅允许 0.6）→ 400 / immutable_param"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "thinking": {"type": "disabled"}, "temperature": 0}
    r = send(client, rec, req)
    _expect_immutable_param(rec, "disabled 模式 temperature=0", r)


def test_32_09_与top_p同时指定(client, rec):
    """temperature：与 top_p 同时指定（均官方默认值 1.0/0.95）→ 2xx（互斥场景行为记录）"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "temperature": 1.0, "top_p": 0.95}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.check("temperature 与 top_p 可同时指定（未观察到互斥拒绝）", True,
              "两个官方默认值同时指定被接受（2xx），行为已记录", soft=True)
