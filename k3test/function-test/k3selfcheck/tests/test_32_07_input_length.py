"""3.2 输入长度：上下文窗口上限、超长截断策略、返回错误码规范。

两个用例均为 heavy（大输入，130k 字符 / ~4.5MB），需 --include-heavy 才执行。
"""

from __future__ import annotations

import pytest

from k3selfcheck.tests._common import (error_body, error_message, expect_4xx,
                                         expect_common_ok, make_long_text, send)

_IN_LIMIT_PROMPT = make_long_text(130_000)
_OVER_LIMIT_PROMPT = make_long_text(4_500_000)  # 约 1.5M+ tokens，超出官方 1M 上下文上限


@pytest.mark.heavy
def test_32_07_上下文窗口内长输入(client, rec, settings):
    """输入长度：~130k 字符长 prompt（上下文窗口内）应 2xx（heavy）"""
    if not settings.include_heavy:
        pytest.skip("需 --include-heavy 运行（130k 字符长输入）")
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content":
                         "请概括以下长文的主题（一句话）。\n\n" + _IN_LIMIT_PROMPT}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["prompt_chars"] = len(req["messages"][0]["content"])


@pytest.mark.heavy
def test_32_07_超出上下文上限极大输入(client, rec, settings):
    """输入长度：超出官方 1M 上下文上限的极大 prompt（~4.5MB，约 1.5M+ tokens）→ 4xx 且错误码规范（期望 context_length_exceeded 类，heavy）"""
    if not settings.include_heavy:
        pytest.skip("需 --include-heavy 运行（~4.5MB 超限输入）")
    req = {"model": client.model, "max_tokens": 16,
           "messages": [{"role": "user", "content": _OVER_LIMIT_PROMPT}]}
    r = send(client, rec, req)
    expect_4xx(rec, "超限输入", r)
    body = error_body(r)
    msg = error_message(body)
    code = ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "")
        code = code or str(body.get("code") or "")
    rec.expect("错误响应体结构化（含 message）", bool(msg), f"body={str(body)[:200]!r}")
    hint = (code + " " + msg).lower()
    rec.check("错误码为 context_length_exceeded 类",
              "context" in hint and ("length" in hint or "token" in hint),
              f"code={code!r} msg={msg[:150]!r}", soft=True)
