"""3.2 鉴权与安全：无效 API Key 返回 401；未传 Authorization 拒绝；错误响应体结构化。"""

from __future__ import annotations

from k3selfcheck.tests._common import error_body, error_message

_MESSAGES = [{"role": "user", "content": "hi"}]
_BAD_KEY = "Bearer sk-invalid-key-0123456789abcdef"


def _expect_auth_rejected(rec, name: str, r) -> None:
    rec.expect(f"{name} 返回 401/403", r.status_code in (401, 403),
               f"status={r.status_code} err={r.error}")
    rec.expect(f"{name} 无网络/超时错误", r.error is None, f"error={r.error!r}")


def test_32_14_错误APIKey(client, rec):
    """鉴权与安全：错误 API Key → 401/403"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 8}
    r = client.chat(req, extra_headers={"Authorization": _BAD_KEY})
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    _expect_auth_rejected(rec, "错误 API Key", r)


def test_32_14_未传Authorization(client, rec):
    """鉴权与安全：不传 Authorization → 401/403"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 8}
    r = client.chat(req, extra_headers={"Authorization": ""})
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    _expect_auth_rejected(rec, "未传 Authorization", r)


def test_32_14_错误响应体结构化(client, rec):
    """鉴权与安全：鉴权错误响应体结构化（含 message）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 8}
    r = client.chat(req, extra_headers={"Authorization": _BAD_KEY})
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    _expect_auth_rejected(rec, "错误 API Key", r)
    body = error_body(r)
    rec.expect("错误响应体为合法 JSON", body is not None,
               f"raw[:200]={(r.raw_text or '')[:200]!r}")
    rec.expect("错误响应体含 message", bool(error_message(body)),
               f"body={str(body)[:200]!r}")


def test_32_14_暴力枚举保护(client, rec):
    """鉴权与安全：连续 20 次错误 API Key 请求均被拒绝（401/403；若触发锁定/429 亦属保护生效，记录）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 8}
    statuses = []
    r = None
    for i in range(20):
        r = client.chat(dict(req),
                        extra_headers={"Authorization": f"Bearer sk-brute-{i:02d}-invalid"})
        statuses.append(r.status_code)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.extra["brute_statuses"] = statuses
    rec.expect("暴力枚举请求全部被拒绝（401/403/429），无放行",
               all(s in (401, 403, 429) for s in statuses), f"statuses={statuses}")
    rec.expect("暴力枚举过程无网络/超时错误", r.error is None, f"error={r.error!r}")
    rec.check("连续无效 Key 后触发锁定/限流（出现 429）", 429 in statuses,
              "20 次连续无效 Key 后未观察到 429（全程稳定 401 拒绝，亦属合规），如实记录",
              soft=True)
