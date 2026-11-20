"""检查项#10 可观测性与复现证据。

每次请求返回可追溯的请求标识：响应体含非空 id（硬）；响应头含 request-id 类
标识（x-request-id/trace 模式匹配，soft）。不要求两端 ID 相同；报告记录脱敏
请求、HTTP、原生 usage、流式终态等完整证据。
"""

from __future__ import annotations

import re

_TRACE_KEY = re.compile(r"(x-request[-_]?id|request[-_]?id|trace|x-trace)", re.IGNORECASE)


def test_k10_observability(client, rec):
    """响应体含非空 id（硬）；响应头含 request-id 类标识（soft）"""
    req = {"model": client.model,
           "messages": [{"role": "user", "content": "你好"}],
           "max_completion_tokens": 256}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")

    body_id = (r.response_json or {}).get("id")
    rec.expect("响应体含非空 id（可追溯请求标识）",
               isinstance(body_id, str) and bool(body_id), f"id={body_id!r}")

    matched = {k: v for k, v in r.response_headers.items() if _TRACE_KEY.search(k)}
    rec.extra["trace_headers"] = matched
    rec.check("响应头含 request-id/trace 类标识",
              bool(matched),
              f"matched={matched or '无'}；all_header_keys={list(r.response_headers)}",
              soft=True)
