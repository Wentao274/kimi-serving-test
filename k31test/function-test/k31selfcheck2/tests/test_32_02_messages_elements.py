"""3.2 messages-元素：messages 数组中元素类型、格式、空值边界校验。"""

from __future__ import annotations

from k31selfcheck2.tests._common import (error_body, error_message, expect_4xx,
                                          expect_common_ok, send)


def test_32_02_content为空字符串(client, rec):
    """messages-元素：content 为空字符串（记录行为，soft）"""
    req = {"model": client.model, "max_tokens": 128,
           "messages": [{"role": "user", "content": ""}]}
    r = send(client, rec, req)
    rec.extra["empty_string_probe"] = {"status_code": r.status_code, "accepted": r.ok,
                                        "content_head": (r.content or "")[:100]}
    if r.ok:
        expect_common_ok(rec, r)
        rec.check("content 为空字符串被接受（行为已记录）", True, "2xx", soft=True)
    else:
        rec.check("content 为空字符串被拒绝（4xx 亦属合法边界处理，行为已记录）",
                  400 <= (r.status_code or 0) < 500,
                  f"status={r.status_code} msg={error_message(error_body(r))[:150]!r}",
                  soft=True)


def test_32_02_content为null(client, rec):
    """messages-元素：content 为 null → 4xx 或接受（记录行为，soft）"""
    req = {"model": client.model, "max_tokens": 128,
           "messages": [{"role": "user", "content": None}]}
    r = send(client, rec, req)
    rec.extra["null_content_probe"] = {"status_code": r.status_code, "accepted": r.ok,
                                        "error": r.error}
    rec.check("content=null 行为已记录（4xx 拒绝或接受均属合法边界处理）",
              r.ok or (r.status_code is not None and 400 <= r.status_code < 500),
              f"status={r.status_code} err={r.error}", soft=True)


def test_32_02_role非法值(client, rec):
    """messages-元素：role 非法值 → 4xx"""
    req = {"model": client.model, "max_tokens": 16,
           "messages": [{"role": "superuser", "content": "你好"}]}
    r = send(client, rec, req)
    expect_4xx(rec, "role 非法值", r)
    rec.extra["error_message"] = error_message(error_body(r))[:200]
