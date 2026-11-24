"""3.2 max_tokens：边界值（0、负数、超出官方上限 131072 的极大值）、显式小值生效、
包含/不含思维链的计数定义差异、max_completion_tokens 兼容性（见 3.1 模型特有特性）。

对齐官方（kimi-k3.1-pro）：max_tokens 默认/上限 131072，显式传 >131072 应被拒绝（4xx）。
"""

from __future__ import annotations

from k31basesuite.tests._common import (error_body, error_message, expect_4xx,
                                          expect_common_ok, send)

_MESSAGES = [{"role": "user", "content": "请写一篇关于春天的长文，尽可能长。"}]


def test_32_06_max_tokens为0(client, rec):
    """max_tokens：边界值 0（期望 4xx 或合法行为，按实际记录）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 0}
    r = send(client, rec, req)
    handled = r.ok or (r.status_code is not None and 400 <= r.status_code < 500)
    rec.expect("max_tokens=0 被妥善处理（4xx 拒绝或 2xx 合法行为，非 5xx/超时）",
               handled and r.error is None, f"status={r.status_code} err={r.error}")
    if r.ok:
        rec.extra["zero_behavior"] = {"finish_reason": r.finish_reason, "usage": r.usage,
                                       "content_head": (r.content or "")[:100]}
        rec.check("max_tokens=0 被接受时的行为（finish_reason/usage 已记录）",
                  True, f"finish={r.finish_reason} usage={r.usage}", soft=True)
    else:
        rec.check("max_tokens=0 被拒绝（4xx）", True,
                  f"status={r.status_code} msg={error_message(error_body(r))[:150]!r}",
                  soft=True)


def test_32_06_max_tokens为负数(client, rec):
    """max_tokens：负数 -1（期望 4xx）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": -1}
    r = send(client, rec, req)
    expect_4xx(rec, "max_tokens=-1", r)


def test_32_06_max_tokens极大值(client, rec):
    """max_tokens：显式传 1048577（>官方最大可设置 1048576）→ 4xx（拒绝超出官方上限）"""
    req = {"model": client.model, "max_tokens": 1048577,
           "messages": [{"role": "user", "content": "用一句话介绍广州。"}]}
    r = send(client, rec, req)
    expect_4xx(rec, "max_tokens=1048577（>1048576）", r)


def test_32_06_显式小值64生效(client, rec):
    """max_tokens：显式小值 64 生效（completion≤64 且 finish=length，hard）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 64}
    r = send(client, rec, req)
    expect_common_ok(rec, r, require_content=False)
    completion = int((r.usage or {}).get("completion_tokens") or 0)
    rec.expect("completion_tokens ≤ 64 且 >0", 0 < completion <= 64,
               f"completion_tokens={completion}")
    rec.expect("finish_reason=length", r.finish_reason == "length",
               f"finish_reason={r.finish_reason!r}")


def test_32_06_思维链计数差异记录(client, rec):
    """max_tokens：包含/不含思维链的计数定义差异——同 max_tokens 下 enabled/disabled 对比（行为记录）"""
    base = {"model": client.model, "max_tokens": 128,
            "messages": [{"role": "user", "content": "请详细分析人工智能的发展史，逐阶段展开。"}]}
    r_on = send(client, rec, {**base, "thinking": {"type": "enabled"}})
    rec.expect("thinking enabled HTTP 2xx", r_on.ok,
               f"status={r_on.status_code} err={r_on.error}")
    c_on = int((r_on.usage or {}).get("completion_tokens") or 0)
    rec.expect("enabled: completion ≤ max_tokens=128 且 >0", 0 < c_on <= 128,
               f"completion_tokens={c_on}")

    r_off = send(client, rec, {**base, "thinking": {"type": "disabled"}})
    expect_common_ok(rec, r_off, require_content=False)
    c_off = int((r_off.usage or {}).get("completion_tokens") or 0)
    rec.expect("disabled: completion ≤ max_tokens=128 且 >0", 0 < c_off <= 128,
               f"completion_tokens={c_off}")

    rec.extra["thinking_token_diff"] = {
        "enabled": {"completion_tokens": c_on,
                    "reasoning_chars": len(r_on.reasoning_content or ""),
                    "content_chars": len(r_on.content or "")},
        "disabled": {"completion_tokens": c_off,
                     "content_chars": len(r_off.content or "")},
    }
    rec.check("思维链计数差异已记录（enabled 含 reasoning_content，disabled 不含）",
              bool(r_on.reasoning_content) and not r_off.reasoning_content,
              f"enabled: reasoning_chars={len(r_on.reasoning_content or '')} "
              f"content_chars={len(r_on.content or '')} completion={c_on}; "
              f"disabled: content_chars={len(r_off.content or '')} completion={c_off}",
              soft=True)
