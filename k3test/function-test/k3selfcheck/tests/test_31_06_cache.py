"""3.1 Cache能力支持：平台侧 Prompt Cache/KV Cache 能力，相同前缀输入复用已缓存结果。

- 相同前缀命中：长前缀请求发送两次，第二次 usage.cached_tokens 应 >0；
- 缓存 TTL（heavy）：立即重发命中后，间隔超过 TTL（默认按 5 分钟估，可用
  KST_CACHE_TTL_WAIT_S 调整）再发相同请求，观察是否仍命中；
缓存粒度、命中延迟/成本优惠、命中率监控接口、是否需主动开启需与平台确认（soft 记录）。
"""

from __future__ import annotations

import os
import time

import pytest

from k3selfcheck.tests._common import expect_common_ok, make_long_text, send

_PREFIX = make_long_text(8000)
_TTL_WAIT_S = float(os.environ.get("KST_CACHE_TTL_WAIT_S", "310"))


def _cached_tokens(usage: dict) -> int:
    details = (usage or {}).get("prompt_tokens_details") or {}
    val = details.get("cached_tokens")
    if val is None:
        val = (usage or {}).get("cached_tokens")
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _req(model: str) -> dict:
    return {"model": model, "max_tokens": 512,
            "messages": [{"role": "user", "content": _PREFIX + "\n\n请用一句话总结上文主题。"}]}


def test_31_06_相同前缀第二次应命中缓存(client, rec):
    """Cache能力支持：相同长前缀请求发送两次，第二次 usage.cached_tokens 应 >0"""
    req = _req(client.model)
    r1 = client.chat(dict(req))
    rec.extra["first_request"] = {"status_code": r1.status_code, "error": r1.error,
                                   "usage": r1.usage,
                                   "cached_tokens": _cached_tokens(r1.usage)}
    rec.expect("首次请求 HTTP 2xx", r1.ok, f"status={r1.status_code} err={r1.error}")

    r2 = send(client, rec, req)
    expect_common_ok(rec, r2)
    second_cached = _cached_tokens(r2.usage)
    rec.extra["second_cached_tokens"] = second_cached
    if second_cached > 0:
        rec.expect("第二次请求命中缓存（cached_tokens>0）", True,
                   f"cached_tokens={second_cached}")
    else:
        rec.check("第二次请求命中缓存（cached_tokens>0）", False,
                  f"cached_tokens={second_cached}：缓存未生效或需主动开启"
                  "（请与平台确认缓存粒度、命中延迟/成本优惠、是否需主动开启）",
                  soft=True)


@pytest.mark.heavy
def test_31_06_缓存TTL过期后不再命中(client, rec, settings):
    """Cache能力支持：缓存 TTL——相同请求立即重发命中后，间隔超过 TTL（默认 5 分钟）再发应不再命中"""
    if not settings.include_heavy:
        pytest.skip(f"需 --include-heavy 运行（含 {_TTL_WAIT_S:.0f}s TTL 过期等待）")

    req = _req(client.model)
    r1 = client.chat(dict(req))
    rec.expect("首次请求 HTTP 2xx", r1.ok, f"status={r1.status_code} err={r1.error}")

    r2 = client.chat(dict(req))
    hit2 = _cached_tokens(r2.usage)
    rec.extra["immediate_second_cached_tokens"] = hit2
    rec.expect("立即重发 HTTP 2xx", r2.ok, f"status={r2.status_code} err={r2.error}")
    if hit2 <= 0:
        pytest.skip(f"立即重发未命中缓存（cached_tokens={hit2}），缓存本身未生效，TTL 行为无法判定")

    rec.extra["ttl_wait_s"] = _TTL_WAIT_S
    time.sleep(_TTL_WAIT_S)

    r3 = send(client, rec, req)
    expect_common_ok(rec, r3)
    third_cached = _cached_tokens(r3.usage)
    rec.extra["after_ttl_cached_tokens"] = third_cached
    rec.check(f"间隔 {_TTL_WAIT_S:.0f}s（>5min TTL）后缓存过期不再命中（cached_tokens=0）",
              third_cached == 0,
              f"cached_tokens={third_cached}（仍命中说明实际 TTL 更长，如实记录，"
              "可加大 KST_CACHE_TTL_WAIT_S 复测）", soft=True)
