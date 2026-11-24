"""响应一致性校验：相同请求在 流式/非流式、重复、并发 场景下的响应一致性
（seed 支持情况以实测为准，一致性如实记录 soft；2xx 与结构有效为 hard）。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from k31basesuite.tests._common import expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "请用三句话介绍机器学习。"}]


def test_33_03_流式与非流式一致性(client, rec):
    """响应一致性：同一请求（seed=42）流式与非流式的 content 一致性（如实记录）"""
    base = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "seed": 42}
    r1 = send(client, rec, {**base, "stream": False})
    expect_common_ok(rec, r1)
    r2 = send(client, rec, {**base, "stream": True})
    expect_common_ok(rec, r2)
    rec.extra["nonstream_content"] = (r1.content or "")[:300]
    rec.extra["stream_content"] = (r2.content or "")[:300]
    rec.check("流式与非流式 content 一致", r1.content == r2.content,
              f"equal={r1.content == r2.content}（确定性依赖 seed 生效，如实记录）", soft=True)


def test_33_03_重复请求一致性(client, rec):
    """响应一致性：seed=42 相同请求连续 3 次 → 均 2xx 且 content 一致（如实记录）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "seed": 42}
    results = []
    for i in range(3):
        r = send(client, rec, dict(req))
        rec.expect(f"第{i + 1}次请求 HTTP 2xx", r.ok,
                   f"status={r.status_code} err={r.error}")
        results.append(r)
    contents = {r.content for r in results}
    rec.check("3 次相同请求 content 一致", len(contents) == 1,
              f"distinct={len(contents)}（确定性依赖 seed 生效，如实记录）", soft=True)


def test_33_03_并发相同请求一致性(client, rec):
    """响应一致性：5 并发相同请求（seed=42）→ 全部 2xx 且 usage 有效、total_tokens 一致（如实记录）"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 2048, "seed": 42}
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: client.chat(dict(req)), range(5)))
    rec.attach_result(req, results[0], client.chat_completions_url, client.masked_headers())
    rec.expect("5 并发全部 HTTP 2xx", all(r.ok for r in results),
               f"statuses={[r.status_code for r in results]}")
    rec.expect("5 并发均无网络/超时错误", all(r.error is None for r in results),
               f"errors={[r.error for r in results][:3]}")
    totals = {(r.usage or {}).get("total_tokens") for r in results}
    rec.extra["total_tokens_set"] = sorted(t for t in totals if t is not None)
    rec.check("5 并发 total_tokens 一致", len(totals) == 1 and None not in totals,
              f"distinct={sorted(totals, key=lambda x: (x is None, x))}（确定性依赖 seed 生效，如实记录）",
              soft=True)
