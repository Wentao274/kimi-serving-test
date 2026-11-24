"""3.2 top_p：kimi-k3.1-pro 官方默认 0.95；非官方默认值应被拒绝（4xx）；越界与类型错误处理。

对齐 kimi-k3.1-pro 官方规格：top_p 仅官方默认值 0.95 被接受，修改为其他值返回 HTTP 4xx。
"""

from __future__ import annotations

from k31basesuite.tests._common import expect_4xx, expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "用一句话介绍南京。"}]


def test_32_03_官方默认0_95接受(client, rec):
    """top_p：显式传官方默认值 0.95 被接受（2xx）"""
    # max_tokens 需容纳 thinking 推理+正文（实测 256 会被推理耗尽导致空 content）
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "top_p": 0.95}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_03_非官方值0_8拒绝(client, rec):
    """top_p：非官方默认值 0.8 → 4xx（官方仅接受 0.95）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16, "top_p": 0.8}
    r = send(client, rec, req)
    expect_4xx(rec, "top_p=0.8（非官方默认）", r)


def test_32_03_越界值1_5(client, rec):
    """top_p：top_p=1.5 越界 → 4xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16, "top_p": 1.5}
    r = send(client, rec, req)
    expect_4xx(rec, "top_p=1.5", r)


def test_32_03_类型错误abc(client, rec):
    """top_p：top_p="abc" 类型错误 → 4xx"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 16, "top_p": "abc"}
    r = send(client, rec, req)
    expect_4xx(rec, "top_p 类型错误", r)
