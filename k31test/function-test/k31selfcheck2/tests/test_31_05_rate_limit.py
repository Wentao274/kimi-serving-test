"""3.1 频控容忍：平台流控（Rate Limiting）容忍策略。

突发 30 并发请求，观察是否触发 429；若触发：429 响应体应结构化、含 Retry-After
头、且立即返回（低延迟）；若未触发：记 soft（容量充足）。限流规则（RPM/TPM/并发
上限）、恢复时间与分级限流策略需与平台确认。
"""

from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor

from k31selfcheck2.tests._common import error_body, error_message

_BURST = 30


def test_31_05_突发30并发频控容忍(client, rec):
    """频控容忍：突发 30 并发请求，记录 429 出现情况与限流响应行为"""
    req = {"model": client.model, "max_tokens": 8,
           "messages": [{"role": "user", "content": "hi"}]}
    with ThreadPoolExecutor(max_workers=_BURST) as pool:
        results = list(pool.map(lambda _: client.chat(dict(req)), range(_BURST)))

    oks = [r for r in results if r.ok]
    r429 = [r for r in results if r.status_code == 429]
    net_errs = [r for r in results if r.error]
    others = [r for r in results if not r.ok and not r.error and r.status_code != 429]

    rec.extra["burst_summary"] = {
        "total": _BURST, "ok": len(oks), "http_429": len(r429),
        "other_status": sorted({r.status_code for r in others}),
        "network_errors": [r.error for r in net_errs][:5],
        "latency_s": {"max": round(max(r.latency_s for r in results), 3),
                       "mean": round(statistics.mean(r.latency_s for r in results), 3)},
    }
    # 附加代表性结果（优先首个 429，否则首个结果）
    rep = r429[0] if r429 else results[0]
    rec.attach_result(req, rep, client.chat_completions_url, client.masked_headers())

    rec.expect("突发并发无网络/超时错误", not net_errs,
               f"errors={[r.error for r in net_errs][:3]}")
    rec.expect("无 5xx 等异常状态", not others,
               f"other_status={sorted({r.status_code for r in others})}")

    if r429:
        structured = all(error_message(error_body(r)) for r in r429)
        rec.expect("429 响应体结构化（含 message）", structured,
                   f"sample={str(error_body(r429[0]))[:200]!r}")
        has_retry = all(any(k.lower() == "retry-after" for k in r.response_headers)
                        for r in r429)
        rec.expect("429 响应含 Retry-After 头", has_retry,
                   f"headers_sample={dict(list(r429[0].response_headers.items())[:10])}")
        max_429_latency = max(r.latency_s for r in r429)
        rec.expect("429 立即返回（低延迟 <10s）", max_429_latency < 10.0,
                   f"max_429_latency={max_429_latency:.3f}s")
        rec.check("未触发限流的请求全部成功", len(oks) + len(r429) == _BURST,
                  f"ok={len(oks)} http_429={len(r429)}", soft=True)
    else:
        rec.expect(f"突发 {_BURST} 并发全部 2xx", len(oks) == _BURST, f"ok={len(oks)}")
        rec.check("未出现 429：突发 30 并发容量充足（或限流阈值更高；限流规则 RPM/TPM/"
                  "并发上限、恢复时间及分级限流策略需与平台确认）",
                  True, "容量观察通过", soft=True)
