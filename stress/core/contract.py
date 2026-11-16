"""客户需求文档中的合同阈值常量（唯一出处，勿随意修改）。

来源：《K3.1 流量外采要求 / K3.1 Serving Requirements》
- 合同要求 2. TTFT 要求（分档表）
- 合同要求 3. OTPS 要求
- 合同要求 5. 429 约定
- 合同要求 6. SLA（10 分钟窗口、失败率 1%）
- Some Tips（起步负载、压测并发、TPM、24h）
"""

from __future__ import annotations

# ---- TTFT 分档（合同第 2 条）：(档位名, uncached 下限含, 上限不含, P50 秒, P90 秒)
TTFT_TIERS = [
    ("<8k",      0,       8_192,    2.0,   4.0),
    ("8k-32k",   8_192,   32_768,   4.0,   6.0),
    ("32k-128k", 32_768,  131_072,  10.0,  20.0),
    ("128k-256k", 131_072, 262_144, 25.0,  45.0),
    ("256k-1m",  262_144, 1_048_577, 35.0, 100.0),
]
TIER_NAMES = [t[0] for t in TTFT_TIERS]

# ---- OTPS（合同第 3 条）
OTPS_MIN = 30.0                 # OTPS 应高于 30（每请求）
OTPS_VIOLATION_RATIO_MAX = 0.01  # 不达标请求占比 >1% → 周期不可用

# ---- SLA（合同第 6 条）
WINDOW_SECONDS = 600            # 连续 10 分钟窗口
FAILURE_RATE_MAX = 0.01         # 窗口失败率 ≥1% → 不可用

# ---- 429（合同第 5 条：即时返回，而不是等待）
TOO_MANY_REQUESTS_P90_MAX_S = 5.0   # 429 响应时延 P90 判定阈值（设计值，可配置）

# ---- Some Tips 测试期基线
BASELINE_RPM = 1000
BASELINE_TPM = 25_000_000
STRESS_CONCURRENCY_MIN = 50
STRESS_TPM_MIN = 100_000_000
PLATFORM_HOURS = 24

# ---- 容量稳定性判定（设计值）：平台期各窗口达成 RPM/目标之比下限
CAPACITY_MIN_RATIO = 0.95


def tier_of(uncached_tokens: int) -> str:
    """按 uncached_tokens 落入 TTFT 档位。"""
    for name, lo, hi, _p50, _p90 in TTFT_TIERS:
        if lo <= uncached_tokens < hi:
            return name
    return TTFT_TIERS[-1][0]


def tier_thresholds(name: str) -> tuple[float, float]:
    for n, _lo, _hi, p50, p90 in TTFT_TIERS:
        if n == name:
            return p50, p90
    raise KeyError(name)
