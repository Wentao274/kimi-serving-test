"""场景二：缓存基线——命中率（90% 前缀重复）+ TTL（缓存存活时长）。

方法（文档第五章）：
1. Warm：~70k tokens 稳定前缀作为 messages[0]，等待响应完成；
2. 命中率：立即 Probe（messages[0] byte-exact 相同 + 追加 assistant+user 尾部轮次），
   hit_rate = cached_tokens / prompt_tokens，达标 ≥85%（参考线 80% 并列展示）；
3. TTL：warm 后间隔 ttl_wait_s（默认 30s）再 Probe，检查仍命中；
4. 可选过期观察点（默认 70s）：对照原厂 ~50s，soft 记录不判定。
"""

from __future__ import annotations

import asyncio

from k31selfstress1.core import dataset


def _hit_rate(usage: dict) -> tuple[int, int, float]:
    pt = int((usage or {}).get("prompt_tokens") or 0)
    details = (usage or {}).get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    if cached is None:
        cached = (usage or {}).get("cached_tokens")
    cached = int(cached or 0)
    return pt, cached, (cached / pt) if pt > 0 else 0.0


async def _warm(client, model: str, warm_text: str, max_tokens: int) -> object:
    payload = {"model": model, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": warm_text}]}
    return await client.chat(payload)


async def _probe(client, model: str, warm_text: str, max_tokens: int) -> object:
    """messages[0] 与 warm byte-exact 相同，追加 assistant+user 尾部轮次（90% 前缀重复）。"""
    payload = {"model": model, "max_tokens": max_tokens,
               "messages": [
                   {"role": "user", "content": warm_text},
                   {"role": "assistant", "content": "已收到，请继续。"},
                   {"role": "user", "content": "请用一句话概括第一段的主旨。"}]}
    return await client.chat(payload)


async def run(client, cfg: dict, log) -> dict:
    cc = cfg["cache"]
    model = cfg["model"]
    records: list[dict] = []

    # warm 文本定长（~warm_tokens）：先按比例估算，校准请求确认后直接使用
    ratio = 2.0
    est_chars = dataset.tokens_to_chars(cc["warm_tokens"], ratio)
    warm_text = dataset.filler_text(est_chars)
    log(f"[cache] warm 前缀 ~{cc['warm_tokens']} tokens（~{len(warm_text)} 字符，估算）")

    # ---- 命中率轮次 ----
    hit_rows = []
    for i in range(cc["hit_rate_rounds"]):
        w = await _warm(client, model, warm_text, cc["warm_max_tokens"])
        if not w.ok:
            log(f"[cache] 命中率轮次 {i + 1}: warm 失败 {w.error or w.status}")
            records.append({"scenario": "cache", "phase": "warm", "round": i + 1,
                            "status": w.status, "error": w.error})
            continue
        p = await _probe(client, model, warm_text, cc["probe_max_tokens"])
        pt, cached, rate = _hit_rate(p.usage)
        row = {"round": i + 1, "status": p.status, "prompt_tokens": pt,
               "cached_tokens": cached, "hit_rate": rate,
               "hit": p.ok and cached > 0, "error": p.error}
        hit_rows.append(row)
        records.append({"scenario": "cache", "phase": "probe", **row})
        log(f"[cache] 命中率轮次 {i + 1}: cached={cached}/{pt} hit_rate={rate:.1%}")

    rates = [r["hit_rate"] for r in hit_rows if r.get("status") == 200 and not r.get("error")]
    avg_rate = sum(rates) / len(rates) if rates else 0.0
    min_rate = min(rates) if rates else 0.0
    hit_pass = bool(rates) and avg_rate >= cc["hit_rate_limit"]

    # ---- TTL 轮次 ----
    ttl_rows = []
    for i in range(cc["ttl_rounds"]):
        w = await _warm(client, model, warm_text, cc["warm_max_tokens"])
        if not w.ok:
            log(f"[cache] TTL 轮次 {i + 1}: warm 失败 {w.error or w.status}")
            continue
        wait = cc["ttl_wait_s"]
        log(f"[cache] TTL 轮次 {i + 1}: warm 完成，等待 {wait}s…")
        await asyncio.sleep(wait)
        p = await _probe(client, model, warm_text, cc["probe_max_tokens"])
        pt, cached, rate = _hit_rate(p.usage)
        hit = p.ok and rate >= cc["ttl_min_hit_rate"]
        row = {"round": i + 1, "wait_s": wait, "status": p.status, "prompt_tokens": pt,
               "cached_tokens": cached, "hit_rate": rate, "hit": hit, "error": p.error}
        ttl_rows.append(row)
        records.append({"scenario": "cache", "phase": "ttl_probe", **row})
        log(f"[cache] TTL 轮次 {i + 1}: {wait}s 后 hit_rate={rate:.1%} hit={hit}")
    ttl_pass = bool(ttl_rows) and all(r["hit"] for r in ttl_rows)

    # ---- 过期观察点（soft）----
    expire_row = None
    if cc.get("ttl_expire_probe_s"):
        w = await _warm(client, model, warm_text, cc["warm_max_tokens"])
        if w.ok:
            wait = cc["ttl_expire_probe_s"]
            log(f"[cache] 过期观察: 等待 {wait}s…")
            await asyncio.sleep(wait)
            p = await _probe(client, model, warm_text, cc["probe_max_tokens"])
            pt, cached, rate = _hit_rate(p.usage)
            expire_row = {"wait_s": wait, "prompt_tokens": pt, "cached_tokens": cached,
                          "hit_rate": rate, "hit": p.ok and cached > 0}
            records.append({"scenario": "cache", "phase": "expire_probe", **expire_row})
            log(f"[cache] 过期观察: {wait}s 后 hit_rate={rate:.1%} hit={expire_row['hit']}")

    passed = hit_pass and ttl_pass
    return {"passed": passed,
            "hit_rate": {"rows": hit_rows, "avg": avg_rate, "min": min_rate,
                         "limit": cc["hit_rate_limit"], "reference": cc["hit_rate_reference"],
                         "passed": hit_pass},
            "ttl": {"rows": ttl_rows, "wait_s": cc["ttl_wait_s"],
                    "min_hit_rate": cc["ttl_min_hit_rate"], "passed": ttl_pass},
            "expire_probe": expire_row,
            "records": records,
            "n_requests": len(records)}
