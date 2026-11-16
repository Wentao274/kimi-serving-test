"""条目#6 Support trace ID（OpenTelemetry）。

原始要求：Other Basic Requirements — 1. Support trace ID (OpenTelemetry)。

实现方法：
- 携带 W3C traceparent 请求头发送请求，服务必须正常受理（不得因未知头报错）；
- 检查响应头/响应体中是否返回 trace 标识（如 x-trace-id / traceparent /
  x-request-id / trace_id 字段）；由于具体 trace 回传方式未在文档中约定，
  该检查为 soft，需人工结合供应商网关文档确认。
"""

from __future__ import annotations

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

_TRACE_HEADER_KEYS = ("x-trace-id", "traceparent", "tracestate", "x-request-id",
                      "x-traceid", "trace-id", "x-b3-traceid")
_TRACE_BODY_KEYS = ("trace_id", "traceId", "request_id", "requestId")


def _minimal_req(model: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK and nothing else."}],
        "max_tokens": 16,
    }


def _find_trace_markers(result) -> list[str]:
    """在响应头与响应体中寻找 trace 标识，返回命中的键名列表。"""
    hits = []
    headers = {k.lower(): v for k, v in (result.response_headers or {}).items()}
    for key in _TRACE_HEADER_KEYS:
        if key in headers:
            hits.append(f"header:{key}")
    body = result.response_json or {}
    for key in _TRACE_BODY_KEYS:
        if key in body:
            hits.append(f"body:{key}")
    return hits


def test_06_traceparent_accepted(client, rec):
    """携带 traceparent 头的请求必须被正常受理（2xx）"""
    req = _minimal_req(client.model)
    result = client.chat(req, extra_headers={"traceparent": TRACEPARENT})
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.extra["injected_traceparent"] = TRACEPARENT
    rec.expect("携带 traceparent 请求 HTTP 2xx", result.ok,
               f"status={result.status_code} err={result.error}")
    hits = _find_trace_markers(result)
    rec.check("响应中发现 trace 标识", bool(hits),
              f"命中={hits or '无'}（回传方式未约定，需人工确认）", soft=True)


def test_06_trace_id_available(client, rec):
    """默认请求下，响应中应可获得 trace/请求标识（soft）"""
    req = _minimal_req(client.model)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    hits = _find_trace_markers(result)
    rec.check("响应中发现 trace/request 标识", bool(hits),
              f"命中={hits or '无'}（回传方式未约定，需人工确认）", soft=True)
