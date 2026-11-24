"""3.2 presence_penalty：kimi-k3.1-pro 官方默认 0；非官方默认值应被拒绝（4xx）；
与 frequency_penalty 官方默认值叠加场景。

对齐 kimi-k3.1-pro 官方规格：presence_penalty 仅官方默认值 0 被接受，修改为其他值返回 HTTP 4xx。
"""

from __future__ import annotations

from k3selfcheck.tests._common import expect_4xx, expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "用一句话介绍无锡。"}]


def test_32_05_官方默认0接受(client, rec):
    """presence_penalty：显式传官方默认值 0 被接受（2xx）"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "presence_penalty": 0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_05_非官方值0_5拒绝(client, rec):
    """presence_penalty：非官方默认值 0.5 → 4xx（官方仅接受 0）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "presence_penalty": 0.5}
    r = send(client, rec, req)
    expect_4xx(rec, "presence_penalty=0.5（非官方默认）", r)


def test_32_05_越界值2_5(client, rec):
    """presence_penalty：2.5 越界（[-2,2] 之外）→ 4xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16,
           "presence_penalty": 2.5}
    r = send(client, rec, req)
    expect_4xx(rec, "presence_penalty=2.5", r)


def test_32_05_与frequency_penalty官方默认叠加(client, rec):
    """presence_penalty：与 frequency_penalty 官方默认值叠加（均 0）被接受（2xx）"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048,
           "presence_penalty": 0, "frequency_penalty": 0}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
