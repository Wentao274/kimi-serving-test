"""3.2 stream_options：include_usage 与 continuous_usage_stats 连续用量统计行为。"""

from __future__ import annotations

from k3selfcheck.tests._common import expect_common_ok, send, sse_chunks

_MESSAGES = [{"role": "user", "content": "请用三句话介绍深度学习。"}]


def test_32_12_include_usage_true(client, rec):
    """stream_options：include_usage=true → 流末 usage 块存在（hard）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": True}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    usage_chunks = [c for c in chunks if c.get("usage")]
    rec.expect("流末存在 usage 块", bool(usage_chunks),
               f"n_usage_chunks={len(usage_chunks)}")
    rec.expect("usage 计数有效（prompt_tokens>0 且 completion_tokens>0）",
               bool(r.usage.get("prompt_tokens")) and bool(r.usage.get("completion_tokens")),
               f"usage={r.usage}")


def test_32_12_include_usage_false(client, rec):
    """stream_options：include_usage=false → 流中无 usage 块（hard）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": False}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    usage_chunks = [c for c in chunks if c.get("usage")]
    rec.expect("流中无 usage 块", not usage_chunks,
               f"n_usage_chunks={len(usage_chunks)} usage={r.usage}")


def test_32_12_continuous_usage_stats(client, rec):
    """stream_options：continuous_usage_stats=true 时每个 chunk 是否带 usage（记录 soft）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": True, "continuous_usage_stats": True}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    n_with_usage = sum(1 for c in chunks if c.get("usage"))
    rec.extra["continuous_usage"] = {"n_chunks": len(chunks), "n_with_usage": n_with_usage}
    rec.check("每个 chunk 均携带 usage（continuous_usage_stats）",
              len(chunks) > 1 and n_with_usage == len(chunks),
              f"n_chunks={len(chunks)} n_with_usage={n_with_usage}"
              "（不支持连续用量统计时记此 soft）", soft=True)
