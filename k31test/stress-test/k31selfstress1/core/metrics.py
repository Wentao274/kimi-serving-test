"""分档聚合与判定：percentile、avg/P50/P90 汇总、判定矩阵条目。"""

from __future__ import annotations


def percentile(values: list[float], q: float) -> float | None:
    """线性插值百分位；空列表返回 None。"""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def agg(values: list[float]) -> dict:
    """avg/P50/P90/min/max/n 汇总。"""
    if not values:
        return {"n": 0, "avg": None, "p50": None, "p90": None, "min": None, "max": None}
    return {
        "n": len(values),
        "avg": sum(values) / len(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "min": min(values),
        "max": max(values),
    }


def judgment(name: str, measured, limit, *, unit: str = "", higher_better: bool = False) -> dict:
    """单条判定：measured vs limit。higher_better=True 时 measured ≥ limit 为通过。"""
    if measured is None:
        return {"name": name, "measured": None, "limit": limit, "unit": unit,
                "passed": None, "detail": "无有效样本，无法判定"}
    ok = measured >= limit if higher_better else measured <= limit
    return {"name": name, "measured": round(measured, 3) if isinstance(measured, float) else measured,
            "limit": limit, "unit": unit, "passed": ok,
            "detail": f"{measured:.1f}{unit} {'≥' if higher_better else '≤'} {limit}{unit}"}
