"""3.2 输入长度-非流式输出：非流式模式下超长输入的响应完整性。"""

from __future__ import annotations

from k31selfcheck2.tests._common import expect_common_ok, make_long_text, send

_LONG_INPUT = make_long_text(512 * 1024)


def test_32_13_非流式512KB长输入响应完整(client, rec):
    """输入长度-非流式输出：非流式 + ~512KB 长 prompt → 2xx 且 content 非空完整（长度阈值内不被截断）"""
    req = {"model": client.model, "max_tokens": 1024,
           "messages": [{"role": "user", "content":
                         "请阅读以下文本，并用一句话说明文本讨论的主题。\n\n" + _LONG_INPUT}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["prompt_chars"] = len(req["messages"][0]["content"])
    rec.expect("响应完整未被截断（finish_reason=stop）", r.finish_reason == "stop",
               f"finish_reason={r.finish_reason!r}")
