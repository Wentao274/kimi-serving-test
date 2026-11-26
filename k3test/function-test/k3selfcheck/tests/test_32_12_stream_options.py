"""3.2 stream_options：include_usage 与 continuous_usage_stats 连续用量统计行为。

usage 检测同时识别两种序列化形态：
- 顶层 usage 块（独立 chunk 的 "usage" 字段）；
- 内嵌 usage（finish chunk 的 choices[].usage 字段，官方在截断场景以此形态返回）。
"""

from __future__ import annotations

from k3selfcheck.tests._common import expect_common_ok, send, sse_chunks

_MESSAGES = [{"role": "user", "content": "请用三句话介绍深度学习。"}]


def _nested_usage(chunk: dict) -> dict | None:
    """内嵌在 choices[].usage 的 usage 字段（若有）。"""
    for ch in chunk.get("choices") or []:
        u = (ch or {}).get("usage")
        if isinstance(u, dict) and u:
            return u
    return None


def _chunk_usage(chunk: dict) -> dict | None:
    """chunk 的 usage（顶层块或 choices 内嵌，两种形态均识别）。"""
    u = chunk.get("usage")
    if isinstance(u, dict) and u:
        return u
    return _nested_usage(chunk)


def test_32_12_include_usage_true(client, rec):
    """stream_options：include_usage=true → 流末 usage 块存在（hard）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": True}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    usage_chunks = [c for c in chunks if _chunk_usage(c)]
    rec.expect("流末存在 usage 块", bool(usage_chunks),
               f"n_usage_chunks={len(usage_chunks)}")
    rec.expect("usage 计数有效（prompt_tokens>0 且 completion_tokens>0）",
               bool(r.usage.get("prompt_tokens")) and bool(r.usage.get("completion_tokens")),
               f"usage={r.usage}")


def test_32_12_include_usage_false(client, rec):
    """stream_options：include_usage=false → 流中无 usage 块（顶层/内嵌两种形态均不得出现）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": False}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    usage_chunks = [c for c in chunks if _chunk_usage(c)]
    rec.expect("流中无 usage 块（含 choices 内嵌形态）", not usage_chunks,
               f"n_usage_chunks={len(usage_chunks)} usage={r.usage}")
    if usage_chunks:
        # 官方也有相同问题（官方在 include_usage=false 时同样返回 usage，choices 内嵌形态）
        rec.check("官方也有相同问题（include_usage=false 时官方同样返回 usage）",
                  True,
                  "供应商=顶层 usage 块；官方=choices 内嵌 usage（双方均违反 include_usage=false 契约）",
                  soft=True)
    # soft 记录：usage 出现形态（顶层独立块 / choices 内嵌），供双方行为比对
    top_level = [c for c in usage_chunks if c.get("usage")]
    nested = [c for c in usage_chunks if not c.get("usage") and _nested_usage(c)]
    rec.extra["usage_form"] = {"top_level_chunks": len(top_level),
                                "nested_in_choices": len(nested),
                                "finish_reason": r.finish_reason}
    rec.check("usage 出现形态记录（顶层独立块 vs choices 内嵌，截断场景常见内嵌）",
              True,
              f"top_level={len(top_level)} nested={len(nested)} finish={r.finish_reason!r}",
              soft=True)


def test_32_12_continuous_usage_stats(client, rec):
    """stream_options：continuous_usage_stats=true 时每个 chunk 是否带 usage（记录 soft）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": True, "continuous_usage_stats": True}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    n_with_usage = sum(1 for c in chunks if _chunk_usage(c))
    rec.extra["continuous_usage"] = {"n_chunks": len(chunks), "n_with_usage": n_with_usage}
    rec.check("每个 chunk 均携带 usage（continuous_usage_stats）",
              len(chunks) > 1 and n_with_usage == len(chunks),
              f"n_chunks={len(chunks)} n_with_usage={n_with_usage}"
              "（不支持连续用量统计时记此 soft）", soft=True)
