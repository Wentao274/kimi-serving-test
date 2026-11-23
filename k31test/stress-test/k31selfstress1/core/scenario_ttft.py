"""场景一：TTFT（按输入长度分档）+ TPOT——同一批流式请求产出两个指标。

流程：校准字符/token 比 → 按档构造输入（唯一 nonce 前缀保证冷请求）→
并发执行 → 按实测 prompt_tokens 归档 → 分档判定（avg/P90 vs 达标线）+ TPOT 判定。
"""

from __future__ import annotations

import asyncio

from k31selfstress1.core import dataset, metrics

# 归档档序：按 prompt_tokens 落入的区间归类（档外样本改归实际档）


def _tier_of(tiers: list[dict], prompt_tokens: int) -> str:
    for t in tiers:
        if t["min"] <= prompt_tokens < t["max"]:
            return t["name"]
    return tiers[-1]["name"] if prompt_tokens >= tiers[-1]["min"] else tiers[0]["name"]


async def _calibrate(client, model: str, log) -> float:
    """校准请求：~20k 字符 → 读 usage.prompt_tokens 得字符/token 比。"""
    text = dataset.filler_text(20_000)
    payload = {"model": model, "max_tokens": 16,
               "messages": [{"role": "user", "content": text + "\n\n请用一句话总结上文。"}]}
    r = await client.chat(payload)
    if r.ok and r.prompt_tokens > 0:
        ratio = dataset.calibrate_ratio(r.prompt_tokens, len(payload["messages"][0]["content"]))
        log(f"[ttft] 校准: prompt_tokens={r.prompt_tokens} chars={len(text)} ratio={ratio:.2f} 字符/token")
        return ratio
    log(f"[ttft] 校准请求失败（{r.error or r.status}），使用兜底 ratio=2.0")
    return 2.0


async def _one_request(client, model: str, cfg: dict, base_text: str,
                       sem: asyncio.Semaphore, records: list, log, tag: str,
                       done: list[int]) -> None:
    nonce = dataset.nonce_prefix()
    payload = {"model": model, "stream": True,
               "max_tokens": cfg["max_tokens"],
               "messages": [{"role": "user", "content":
                             f"{nonce}\n\n{base_text}\n\n请用一句话总结上文。"}]}
    if cfg.get("include_usage"):
        payload["stream_options"] = {"include_usage": True}
    async with sem:
        r = await client.stream_chat(payload)
    records.append({
        "scenario": "ttft", "planned_tier": tag,
        "prompt_tokens": r.prompt_tokens, "cached_tokens": r.cached_tokens,
        "completion_tokens": r.completion_tokens,
        "ttft_ms": r.ttft_ms, "tpot_ms": r.tpot_ms, "total_ms": r.total_ms,
        "status": r.status, "finish_reason": r.finish_reason,
        "cold_ok": (r.cached_tokens == 0), "error": r.error,
    })
    done[0] += 1
    if done[0] % 50 == 0:
        log(f"[ttft] {tag}: {done[0]} 请求已完成")


def _judge_tier(name: str, samples: list[dict], baseline: dict) -> dict:
    """单档判定：avg ≤ avg_limit 且 P90 ≤ p90_limit。"""
    ttfts = [s["ttft_ms"] for s in samples if s["ttft_ms"] is not None]
    a = metrics.agg(ttfts)
    j_avg = metrics.judgment(f"TTFT {name} avg", a["avg"], baseline["avg_limit"], unit="ms")
    j_p90 = metrics.judgment(f"TTFT {name} P90", a["p90"], baseline["p90_limit"], unit="ms")
    passed = (j_avg["passed"] is True) and (j_p90["passed"] is True)
    return {"name": name, "n": len(samples), "n_valid_ttft": len(ttfts),
            "avg_ms": a["avg"], "p90_ms": a["p90"], "min_ms": a["min"], "max_ms": a["max"],
            "baseline_avg": baseline["avg"], "baseline_p90": baseline["p90"],
            "avg_limit": baseline["avg_limit"], "p90_limit": baseline["p90_limit"],
            "judgments": [j_avg, j_p90], "passed": passed,
            "ttft_series": [round(v, 1) for v in ttfts]}


async def run(client, cfg: dict, log) -> dict:
    tt = cfg["ttft_tpot"]
    model = cfg["model"]
    quick = tt.get("quick_mode")
    baselines = tt["baselines"]

    log(f"[ttft] 开始 TTFT/TPOT 场景 | mode={'quick' if quick else 'full'} "
        f"concurrency={tt['concurrency']} include_usage={tt.get('include_usage')}")
    ratio = await _calibrate(client, model, log)

    # 计划：[(档名, 目标 tokens, 样本数, 判定基线)]
    if quick:
        plan = []
        for target in tt["quick_tiers_tokens"]:
            tier_name = _tier_of(tt["tiers"], target)
            plan.append((f"{target // 1000}k(quick→{tier_name})", target,
                         tt["quick_samples"], baselines[tier_name]))
    else:
        n = tt["samples_per_tier"]
        plan = [(t["name"], t["target"], n, baselines[t["name"]]) for t in tt["tiers"]]

    sem = asyncio.Semaphore(tt["concurrency"])
    all_records: list[dict] = []
    tier_results = []

    for tag, target_tokens, samples, baseline in plan:
        chars = dataset.tokens_to_chars(target_tokens, ratio)
        base_text = dataset.filler_text(chars)
        records: list[dict] = []
        done = [0]
        log(f"[ttft] tier={tag} target={target_tokens} tokens(~{chars} 字符) samples={samples}")
        t0 = asyncio.get_event_loop().time()
        await asyncio.gather(*[
            _one_request(client, model, tt, base_text, sem, records, log, tag, done)
            for _ in range(samples)
        ])
        elapsed = asyncio.get_event_loop().time() - t0
        ok = [s for s in records if s["status"] == 200 and s["error"] is None]
        cold_bad = [s for s in ok if not s["cold_ok"]]
        log(f"[ttft] tier={tag} 完成 {len(records)} 请求（成功 {len(ok)}，"
            f"冷请求违例 {len(cold_bad)}）耗时 {elapsed:.1f}s")

        # 有效性：成功样本 < min_valid_ratio × 计划 → FAIL（证据不足）
        valid_ratio = len(ok) / max(samples, 1)
        tr = _judge_tier(tag, ok, baseline)
        tr["n_planned"] = samples
        tr["n_ok"] = len(ok)
        tr["n_cold_violation"] = len(cold_bad)
        if valid_ratio < tt.get("min_valid_ratio", 0.9):
            tr["passed"] = False
            tr["judgments"].append({
                "name": f"TTFT {tag} 样本有效性", "measured": f"{valid_ratio:.0%}",
                "limit": f"≥{tt.get('min_valid_ratio', 0.9):.0%}", "unit": "",
                "passed": False, "detail": "成功样本不足，证据不足"})
        tier_results.append(tr)
        all_records.extend(records)

    # TPOT：全部成功样本
    tpots = [s["tpot_ms"] for s in all_records
             if s.get("tpot_ms") is not None and s["status"] == 200]
    a = metrics.agg(tpots)
    lim = tt["tpot_limits"]
    j_avg = metrics.judgment("TPOT avg", a["avg"], lim["avg"], unit="ms")
    j_p50 = metrics.judgment("TPOT P50", a["p50"], lim["p50"], unit="ms")
    j_p90 = metrics.judgment("TPOT P90", a["p90"], lim["p90"], unit="ms")
    tpot_result = {"n": len(tpots), "avg_ms": a["avg"], "p50_ms": a["p50"], "p90_ms": a["p90"],
                   "baseline": {"avg": 25, "p50": 29, "p90": 35}, "limits": lim,
                   "judgments": [j_avg, j_p50, j_p90],
                   "passed": all(j["passed"] is True for j in (j_avg, j_p50, j_p90)),
                   "series": [round(v, 2) for v in tpots]}
    log(f"[ttft] TPOT: avg={a['avg'] and round(a['avg'], 1)}ms p50={a['p50']} p90={a['p90']} | "
        f"{'PASS' if tpot_result['passed'] else 'FAIL'}")

    passed = all(t["passed"] for t in tier_results) and tpot_result["passed"]
    return {"passed": passed, "tiers": tier_results, "tpot": tpot_result,
            "records": all_records,
            "n_requests": len(all_records),
            "n_failed": sum(1 for s in all_records if s["status"] != 200 or s["error"])}
