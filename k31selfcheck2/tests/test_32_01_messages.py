"""3.2 messages：基础对话消息结构正常处理，role/content 必填项校验。"""

from __future__ import annotations

from k31selfcheck2.tests._common import (error_body, error_message, expect_4xx,
                                          expect_common_ok, send)


def test_32_01_基础对话消息结构(client, rec):
    """messages：role/content 必填结构正常处理（2xx）"""
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content": "你好，请用一句话自我介绍。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_01_缺role必填项校验(client, rec):
    """messages：缺 role → 4xx（必填项校验）"""
    req = {"model": client.model, "max_tokens": 16,
           "messages": [{"content": "你好"}]}
    r = send(client, rec, req)
    expect_4xx(rec, "缺 role", r)
    rec.extra["error_message"] = error_message(error_body(r))[:200]


def test_32_01_缺content必填项校验(client, rec):
    """messages：缺 content → 4xx（必填项校验）"""
    req = {"model": client.model, "max_tokens": 16,
           "messages": [{"role": "user"}]}
    r = send(client, rec, req)
    expect_4xx(rec, "缺 content", r)
    rec.extra["error_message"] = error_message(error_body(r))[:200]
