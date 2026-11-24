"""3.2 stream：chunk 格式规范、每个 chunk 是否包含 usage、流式中断处理、SSE 协议合规。"""

from __future__ import annotations

from k3selfcheck.tests._common import expect_common_ok, send, sse_chunks

_MESSAGES = [{"role": "user", "content": "请用三句话介绍机器学习。"}]


def test_32_08_流式SSE协议合规(client, rec):
    """stream：流式 chunk 为合法 SSE（data: 行、chat.completion.chunk 结构、[DONE]）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    raw = r.raw_text or ""
    non_empty_lines = [l for l in raw.splitlines() if l.strip()]
    rec.expect("SSE 非空行均为 data: 行",
               all(l.startswith("data:") for l in non_empty_lines),
               f"non_data_lines={[l for l in non_empty_lines if not l.startswith('data:')][:3]}")
    rec.expect("流以 data: [DONE] 结束", raw.rstrip().endswith("data: [DONE]"),
               f"tail={raw.rstrip()[-80:]!r}")
    chunks = sse_chunks(raw)
    rec.expect("data 负载均为合法 JSON chunk", len(chunks) > 0 and len(chunks) == r.n_chunks,
               f"parsed={len(chunks)} n_chunks={r.n_chunks}")
    bad = [c for c in chunks if c.get("object") not in (None, "chat.completion.chunk")]
    rec.expect("chunk.object=chat.completion.chunk", not bad,
               f"bad_objects={[c.get('object') for c in bad][:3]}")
    rec.expect("收到多个 chunk（n_chunks>0）", r.n_chunks > 0, f"n_chunks={r.n_chunks}")
    rec.expect("finish_reason 存在", bool(r.finish_reason),
               f"finish_reason={r.finish_reason!r}")


def test_32_08_include_usage末块usage(client, rec):
    """stream：include_usage=true 时 usage 末块存在"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True,
           "stream_options": {"include_usage": True}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    chunks = sse_chunks(r.raw_text or "")
    usage_chunks = [c for c in chunks if c.get("usage")]
    rec.expect("流末存在 usage 块", bool(usage_chunks),
               f"n_usage_chunks={len(usage_chunks)}")
    rec.expect("usage 含 prompt_tokens/completion_tokens",
               bool(r.usage.get("prompt_tokens")) and bool(r.usage.get("completion_tokens")),
               f"usage={r.usage}")


def test_32_08_流式中断行为记录(client, rec):
    """stream：流式请求被中断的行为记录（正常完成即可；真实中断注入属专项测试）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "stream": True}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.expect("流式正常完成（finish_reason=stop 且 [DONE] 到达）",
               r.finish_reason == "stop" and (r.raw_text or "").rstrip().endswith("data: [DONE]"),
               f"finish_reason={r.finish_reason!r}")
    rec.check("流式中断行为：本用例仅验证正常完成路径；客户端中断/网络中断注入需专项混沌测试补充",
              True, "正常完成路径通过", soft=True)
