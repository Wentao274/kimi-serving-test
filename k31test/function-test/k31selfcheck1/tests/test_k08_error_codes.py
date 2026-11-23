"""检查项#8 错误码与异常响应。

分别验证实际 HTTP 状态与原生错误结构：错误 API key → 401/403；未知模型名 → 4xx；
非法参数（temperature=99）→ 400。错误响应体应含结构化 error 信息（message/type
字段），错误文案不要求逐字一致，但须保留原文。
"""

from __future__ import annotations

import json

from engineering.core.client import VendorClient

_MESSAGES = [{"role": "user", "content": "hi"}]


def _parse_error_body(rec, raw_text: str, source: str) -> dict | None:
    try:
        body = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        rec.check(f"{source} 错误响应体为合法 JSON", False,
                  f"raw[:300]={raw_text[:300]!r}", soft=True)
        return None
    return body if isinstance(body, dict) else None


def _check_error_structure(rec, body: dict | None, source: str) -> None:
    """错误体应含结构化 error 信息（message 字段，type 字段若存在则记录）。"""
    if body is None:
        rec.expect(f"{source} 错误响应体为结构化 JSON", False, "响应体非 JSON")
        return
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    has_message = isinstance(err.get("message"), str) and bool(err.get("message"))
    rec.expect(f"{source} 错误体含 message 字段（可定位原因）", has_message,
               f"error_keys={list(err)} body[:300]={json.dumps(body, ensure_ascii=False)[:300]}")
    rec.check(f"{source} 错误体含 type/code 字段（若有则记录）",
              bool(err.get("type") or err.get("code")),
              f"type={err.get('type')!r} code={err.get('code')!r}", soft=True)


def test_k08_invalid_api_key(client, rec):
    """错误 API key → 401/403，错误体含结构化信息"""
    bad = VendorClient(client.base_url, "sk-invalid-key-for-selfcheck", client.model,
                       client.timeout)
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 32}
    r = bad.chat(req)
    rec.attach_result(req, r, bad.chat_completions_url, bad.masked_headers())
    rec.expect("HTTP 状态为 401/403（认证失败）",
               r.status_code in (401, 403), f"status={r.status_code} err={r.error}")
    _check_error_structure(rec, _parse_error_body(rec, r.raw_text, "认证失败"), "认证失败")


def test_k08_unknown_model(client, rec):
    """未知模型名 → 4xx，错误体含结构化信息"""
    req = {"model": "kimi-k3.1-pro-nonexistent-model", "messages": _MESSAGES,
           "max_completion_tokens": 32}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 状态为 4xx（未知模型）",
               r.status_code is not None and 400 <= r.status_code < 500,
               f"status={r.status_code} err={r.error}")
    _check_error_structure(rec, _parse_error_body(rec, r.raw_text, "未知模型"), "未知模型")


def test_k08_illegal_temperature(client, rec):
    """非法参数 temperature=99 → 400（或 4xx），错误体含结构化信息"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 32,
           "temperature": 99}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 状态为 4xx（非法参数被拒绝，不得 200 放行）",
               r.status_code is not None and 400 <= r.status_code < 500,
               f"status={r.status_code} err={r.error}")
    rec.check("HTTP 状态精确为 400", r.status_code == 400,
              f"status={r.status_code}", soft=True)
    _check_error_structure(rec, _parse_error_body(rec, r.raw_text, "非法参数"), "非法参数")
