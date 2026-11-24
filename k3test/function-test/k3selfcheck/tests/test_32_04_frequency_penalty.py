"""3.2 frequency_penalty：kimi-k3.1-pro 官方默认 0；非官方默认值应被拒绝（4xx）；越界与类型错误处理。

对齐 kimi-k3.1-pro 官方规格：frequency_penalty 仅官方默认值 0 被接受，修改为其他值返回 HTTP 4xx。
"""

from __future__ import annotations

from k3selfcheck.tests._common import expect_4xx, expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "用一句话介绍苏州。"}]


def test_32_04_官方默认0接受(client, rec):
    """frequency_penalty：显式传官方默认值 0 被接受（2xx）"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "frequency_penalty": 0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_04_非官方值0_5拒绝(client, rec):
    """frequency_penalty：非官方默认值 0.5 → 4xx（官方仅接受 0）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "frequency_penalty": 0.5}
    r = send(client, rec, req)
    expect_4xx(rec, "frequency_penalty=0.5（非官方默认）", r)


def test_32_04_越界值2_5(client, rec):
    """frequency_penalty：2.5 越界（[-2,2] 之外）→ 4xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "frequency_penalty": 2.5}
    r = send(client, rec, req)
    expect_4xx(rec, "frequency_penalty=2.5", r)


def test_32_04_类型错误abc(client, rec):
    """frequency_penalty："abc" 类型错误 → 4xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "frequency_penalty": "abc"}
    r = send(client, rec, req)
    expect_4xx(rec, "frequency_penalty 类型错误", r)
