"""3.2 json_object：response_format 指定 JSON 模式的合规输出、非法 JSON 处理。"""

from __future__ import annotations

import json

from k31selfcheck2.tests._common import (error_body, error_message,
                                          expect_common_ok, send)


def test_32_11_json_object合规输出(client, rec):
    """json_object：response_format.type=json_object → 响应为非空合法 JSON"""
    req = {"model": client.model, "max_tokens": 1024,
           "messages": [{"role": "user", "content":
                         "请以 JSON 格式返回一本虚构图书的信息，包含 title 与 author 字段。"}],
           "response_format": {"type": "json_object"}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    obj = None
    try:
        obj = json.loads(r.content)
        rec.expect("输出为合法 JSON", True, "")
    except (json.JSONDecodeError, TypeError) as exc:
        rec.expect("输出为合法 JSON", False, f"{exc}; text[:200]={(r.content or '')[:200]!r}")
    if obj is not None:
        rec.expect("输出为非空 JSON 对象", isinstance(obj, dict) and bool(obj),
                   f"parsed={obj}")


def test_32_11_非法response_format类型(client, rec):
    """json_object：非法 response_format 类型（如 "yaml"）→ 4xx 或忽略（记录实际行为）"""
    req = {"model": client.model, "max_tokens": 128,
           "messages": [{"role": "user", "content": "用一句话介绍西安。"}],
           "response_format": {"type": "yaml"}}
    r = send(client, rec, req)
    handled = r.ok or (r.status_code is not None and 400 <= r.status_code < 500)
    rec.expect('非法 response_format.type="yaml" 被妥善处理（4xx 拒绝或忽略，非 5xx/超时）',
               handled and r.error is None, f"status={r.status_code} err={r.error}")
    if r.ok:
        expect_common_ok(rec, r)
        rec.check('非法类型 "yaml" 被拒绝（4xx）', False,
                  "实际行为：被忽略/接受（2xx），如实记录", soft=True)
    else:
        rec.check('非法类型 "yaml" 被拒绝（4xx）', True,
                  f"实际行为：拒绝 status={r.status_code} "
                  f"msg={error_message(error_body(r))[:150]!r}", soft=True)
