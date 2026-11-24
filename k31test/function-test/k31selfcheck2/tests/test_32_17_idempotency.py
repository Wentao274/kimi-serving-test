"""3.2 幂等性验证：相同请求（含 seed 参数）的结果稳定性；重复提交同一请求不产生重复计费。

说明：kimi-k3.1-pro 采样参数仅接受官方默认值（temperature 默认 1.0），本模块不再附加
temperature 参数；seed 确定性支持情况以实测为准，一致性结果如实记录（soft），
2xx 与 usage 有效性为 hard。
"""

from __future__ import annotations

import httpx

from k31selfcheck2.tests._common import expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "请用三句话介绍量子计算。"}]


def test_32_17_seed相同请求结果稳定(client, rec):
    """幂等性验证：带 seed=42 的相同请求两次 → 记录两次 content 一致性（如实记录，soft）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "seed": 42}
    r1 = client.chat(dict(req))
    rec.expect("第一次请求 HTTP 2xx", r1.ok, f"status={r1.status_code} err={r1.error}")
    r2 = send(client, rec, req)
    expect_common_ok(rec, r2)
    rec.extra["first_content"] = (r1.content or "")[:300]
    rec.extra["second_content"] = (r2.content or "")[:300]
    rec.check("带 seed=42 的相同请求两次 content 一致（结果稳定性）",
              r1.content == r2.content,
              f"equal={r1.content == r2.content}（seed 确定性以实测为准，如实记录）",
              soft=True)


def test_32_17_重复提交不重复计费(client, rec):
    """幂等性验证：重复提交同请求两次 → 两次 usage.total_tokens 比对（一致性如实记录，soft）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "seed": 42}
    r1 = client.chat(dict(req))
    rec.expect("第一次请求 HTTP 2xx", r1.ok, f"status={r1.status_code} err={r1.error}")
    r2 = send(client, rec, req)
    expect_common_ok(rec, r2)
    t1 = (r1.usage or {}).get("total_tokens")
    t2 = (r2.usage or {}).get("total_tokens")
    rec.expect("两次请求均返回有效 usage.total_tokens", bool(t1) and bool(t2),
               f"total_tokens: first={t1} second={t2}")
    rec.extra["total_tokens"] = {"first": t1, "second": t2}
    rec.check("重复提交同请求两次 total_tokens 一致（不重复计费）", t1 == t2,
              f"first={t1} second={t2}（确定性依赖 seed 生效，结果如实记录）", soft=True)


def test_32_17_网络重试后行为一致(client, rec):
    """幂等性验证：流式请求客户端中断后，重发相同请求应正常响应（网络重试行为一致）"""
    url = client.chat_completions_url
    headers = {"Authorization": f"Bearer {client.api_key}",
               "Content-Type": "application/json"}
    stream_req = {"model": client.model, "messages": _MESSAGES,
                  "max_tokens": 2048, "stream": True}
    aborted = False
    with httpx.Client(timeout=60) as hc:
        with hc.stream("POST", url, headers=headers, json=stream_req) as resp:
            rec.expect("首次流式请求 HTTP 200", resp.status_code == 200,
                       f"status={resp.status_code}")
            for i, _line in enumerate(resp.iter_lines()):
                if i >= 1:
                    break  # 读取少量 chunk 后立即中断连接
            aborted = True
    rec.extra["aborted_mid_stream"] = aborted

    r = send(client, rec, {"model": client.model, "messages": _MESSAGES,
                           "max_tokens": 2048})
    expect_common_ok(rec, r)
    rec.expect("中断后重发相同请求正常响应（usage 完整）",
               bool((r.usage or {}).get("total_tokens")), f"usage={r.usage}")
