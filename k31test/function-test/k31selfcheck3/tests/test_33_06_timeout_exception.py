"""超时与异常处理：非法请求体/错误 Content-Type/客户端短超时后的服务可用性。"""

from __future__ import annotations

import httpx

from k31basesuite.tests._common import (error_body, error_message,
                                         expect_common_ok, send)

_MESSAGES = [{"role": "user", "content": "用一句话介绍北京。"}]


def test_33_06_非法JSON请求体(client, rec):
    """超时与异常：POST 体为损坏 JSON → 4xx 且错误体结构化"""
    url = client.chat_completions_url
    headers = {"Authorization": f"Bearer {client.api_key}",
               "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=30) as hc:
            resp = hc.post(url, headers=headers,
                           content=b'{"model": "x", "messages": [BROKEN_JSON')
        status = resp.status_code
        raw = resp.text
    except httpx.HTTPError as exc:
        status, raw = None, str(exc)
    rec.extra["broken_json"] = {"status": status, "raw_head": raw[:200]}
    rec.expect("损坏 JSON 请求体返回 4xx",
               status is not None and 400 <= status < 500, f"status={status}")
    try:
        body = __import__("json").loads(raw)
    except Exception:
        body = None
    rec.expect("错误响应体为合法 JSON", isinstance(body, dict),
               f"raw[:200]={raw[:200]!r}")


def test_33_06_错误ContentType行为记录(client, rec):
    """超时与异常：Content-Type=text/plain 发送 JSON 体 → 妥善处理（4xx 或接受，记录）"""
    url = client.chat_completions_url
    headers = {"Authorization": f"Bearer {client.api_key}",
               "Content-Type": "text/plain"}
    payload = ("{\"model\": \"%s\", \"max_tokens\": 8, "
               "\"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}" % client.model)
    try:
        with httpx.Client(timeout=30) as hc:
            resp = hc.post(url, headers=headers, content=payload.encode())
        status = resp.status_code
    except httpx.HTTPError as exc:
        status = None
        rec.expect("错误 Content-Type 被妥善处理（非网络异常）", False, f"{exc}")
        return
    rec.extra["wrong_content_type_status"] = status
    handled = 200 <= status < 300 or 400 <= status < 500
    rec.expect("错误 Content-Type 被妥善处理（2xx 或 4xx，非 5xx）", handled,
               f"status={status}")


def test_33_06_客户端短超时后服务可用(client, rec):
    """超时与异常：客户端 2s 短超时中断长请求后，后续正常请求不受影响"""
    url = client.chat_completions_url
    headers = {"Authorization": f"Bearer {client.api_key}",
               "Content-Type": "application/json"}
    slow_req = {"model": client.model, "max_tokens": 131072,
                "messages": [{"role": "user", "content":
                              "请从 1 开始数到 100000，每个数字独占一行，不要停止。"}]}
    timeout_hit = False
    try:
        with httpx.Client(timeout=2.0) as hc:
            hc.post(url, headers=headers, json=slow_req)
    except (httpx.TimeoutException, httpx.HTTPError):
        timeout_hit = True
    rec.extra["short_timeout_observed"] = timeout_hit
    rec.check("客户端 2s 短超时中断长请求（记录是否命中超时）", timeout_hit,
              f"timeout_hit={timeout_hit}（未命中：服务响应快于 2s，如实记录）", soft=True)

    r = send(client, rec, {"model": client.model, "messages": _MESSAGES, "max_tokens": 256})
    expect_common_ok(rec, r)
    rec.expect("短超时中断后后续请求正常（服务可用性不受影响）", True, "")
