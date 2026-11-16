"""指标聚合与判定：逐请求指标 → 10 分钟窗口 → 合同口径判定。

窗口口径（合同第 6 条）：连续 10 分钟（默认 600s 滚动分桶，demo 可调小）。
判定口径（压力测试条款 + 合同 2/3/5/6 条 + 设计判定矩阵）：
- 容量：平台期各窗口达成 RPM ≥ 目标 × capacity_min_ratio（无 >10min 塌陷）
- TTFT：各 uncached 档位 P50/P90 达标（逐窗口）
- OTPS：窗口不达标（<30）请求占比 ≤1%
- 失败率：窗口 <1%（TPM ≤ 阈值：非 2xx 为失败；TPM > 阈值：2xx/429 之外为失败）
- 429：脉冲期 429 响应时延 P90 ≤ 阈值（默认 5s，"立即返回"）
- 质量：四项检测零确认事故
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .contract import TIER_NAMES, tier_of, tier_thresholds


@dataclass
class RequestMetric:
    ts: float
    phase: str
    session_id: str
    scenario: str
    tier: str
    status: int | None
    ttft_s: float | None
    gen_s: float | None
    total_s: float
    otps: float | None
    prompt_tokens: int | None
    cached_tokens: int | None
    completion_tokens: int | None
    uncached_tokens: int | None
    finish_reason: str | None
    failure: bool
    quality_flags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class _Reservoir:
    """蓄水池采样，限制单档窗口样本量（24h × 1000RPM 全量过大）。"""

    def __init__(self, cap: int = 5000):
        self.cap = cap
        self.values: list[float] = []
        self.seen = 0
        self._rng = random.Random(42)

    def add(self, v: float) -> None:
        self.seen += 1
        if len(self.values) < self.cap:
            self.values.append(v)
        else:
            j = self._rng.randint(0, self.seen - 1)
            if j < self.cap:
                self.values[j] = v

    def quantile(self, q: float) -> float | None:
        if not self.values:
            return None
        s = sorted(self.values)
        idx = min(int(q * len(s)), len(s) - 1)
        return s[idx]


class Window:
    """单个 10 分钟窗口的聚合。"""

    def __init__(self, window_id: int, start_ts: float, end_ts: float):
        self.window_id = window_id
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.total = 0
        self.failures = 0
        self.status_2xx = 0
        self.status_429 = 0
        self.status_other = 0
        self.errors = 0
        self.ttft_by_tier: dict[str, _Reservoir] = {t: _Reservoir() for t in TIER_NAMES}
        self.otps_valid = 0
        self.otps_violations = 0
        self.prompt_tokens_sum = 0
        self.cached_tokens_sum = 0
        self.uncached_tokens_sum = 0
        self.completion_tokens_sum = 0
        self.tpm_samples: list[tuple[float, int]] = []      # (ts, uncached+completion)
        self.latency_429 = _Reservoir()
        self.quality_incidents = 0
        self.quality_by_kind: dict[str, int] = {}
        self.phase_counts: dict[str, int] = {}

    def add(self, m: RequestMetric) -> None:
        self.total += 1
        self.phase_counts[m.phase] = self.phase_counts.get(m.phase, 0) + 1
        if m.failure:
            self.failures += 1
        if m.status is None:
            self.errors += 1
        elif 200 <= m.status < 300:
            self.status_2xx += 1
        elif m.status == 429:
            self.status_429 += 1
            if m.ttft_s is not None:
                self.latency_429.add(m.ttft_s)
        else:
            self.status_other += 1
        if m.uncached_tokens is not None:
            tier = m.tier if m.tier else tier_of(m.uncached_tokens)
            if m.ttft_s is not None and m.status is not None and 200 <= m.status < 300:
                self.ttft_by_tier[tier].add(m.ttft_s)
            self.uncached_tokens_sum += m.uncached_tokens
        if m.otps is not None and m.status is not None and 200 <= m.status < 300:
            self.otps_valid += 1
            if m.otps < 30.0:
                self.otps_violations += 1
        self.prompt_tokens_sum += m.prompt_tokens or 0
        self.cached_tokens_sum += m.cached_tokens or 0
        self.completion_tokens_sum += m.completion_tokens or 0
        if m.uncached_tokens is not None:
            self.tpm_samples.append((m.ts, m.uncached_tokens + (m.completion_tokens or 0)))
        for f in m.quality_flags:
            self.quality_incidents += 1
            self.quality_by_kind[f] = self.quality_by_kind.get(f, 0) + 1

    @property
    def duration_s(self) -> float:
        return max(self.end_ts - self.start_ts, 1.0)

    def snapshot(self) -> dict:
        ttft = {}
        for tier in TIER_NAMES:
            r = self.ttft_by_tier[tier]
            p50_t, p90_t = tier_thresholds(tier)
            ttft[tier] = {
                "n": r.seen,
                "p50": _round(r.quantile(0.5)),
                "p90": _round(r.quantile(0.9)),
                "p50_max": p50_t,
                "p90_max": p90_t,
                "pass": (r.seen == 0) or (
                    (r.quantile(0.5) or 0) <= p50_t and (r.quantile(0.9) or 0) <= p90_t),
            }
        rpm = self.total / (self.duration_s / 60.0)
        tpm = (self.prompt_tokens_sum + self.completion_tokens_sum) / (self.duration_s / 60.0)
        uncached_itpm = self.uncached_tokens_sum / (self.duration_s / 60.0)
        return {
            "window_id": self.window_id,
            "start": time.strftime("%H:%M:%S", time.localtime(self.start_ts)),
            "end_ts": self.end_ts,
            "complete": self.end_ts <= time.time(),
            "phase_counts": dict(self.phase_counts),
            "total": self.total,
            "rpm": round(rpm, 1),
            "tpm": round(tpm, 0),
            "uncached_itpm": round(uncached_itpm, 0),
            "failures": self.failures,
            "failure_rate": round(self.failures / max(self.total, 1), 4),
            "status": {"2xx": self.status_2xx, "429": self.status_429,
                       "other": self.status_other, "errors": self.errors},
            "ttft": ttft,
            "otps_valid": self.otps_valid,
            "otps_violation_ratio": round(self.otps_violations / max(self.otps_valid, 1), 4),
            "latency_429_p90": _round(self.latency_429.quantile(0.9)),
            "quality_incidents": self.quality_incidents,
            "quality_by_kind": dict(self.quality_by_kind),
        }


def _round(v):
    return round(v, 3) if isinstance(v, float) else v


class Aggregator:
    """会话级聚合：窗口分桶 + 逐请求 JSONL 落盘 + 质量事故清单。"""

    def __init__(self, run_start: float, window_s: int = 600,
                 load_threshold_tpm: int = 0):
        self.run_start = run_start
        self.window_s = window_s
        self.load_threshold_tpm = load_threshold_tpm
        self.windows: dict[int, Window] = {}
        self.total_requests = 0
        self.quality_incidents: list = []

    def _window_for(self, ts: float) -> Window:
        wid = int((ts - self.run_start) // self.window_s)
        if wid not in self.windows:
            start = self.run_start + wid * self.window_s
            self.windows[wid] = Window(wid, start, start + self.window_s)
        return self.windows[wid]

    def add(self, m: RequestMetric, phase_tpm_now: float = 0.0) -> None:
        # 失败定义（合同第 6 条）：按当前 TPM 与负载阈值的关系切换口径
        if m.status is None:
            m.failure = True
        elif phase_tpm_now <= self.load_threshold_tpm:
            m.failure = not (200 <= m.status < 300)
        else:
            m.failure = not (200 <= m.status < 300 or m.status == 429)
        self.total_requests += 1
        self._window_for(m.ts).add(m)

    def add_incident(self, incident) -> None:
        if len(self.quality_incidents) < 500:
            self.quality_incidents.append(incident)

    def snapshots(self) -> list[dict]:
        return [self.windows[k].snapshot() for k in sorted(self.windows)]

    def phase_windows(self, phase: str, only_complete: bool = True) -> list[dict]:
        """归属某阶段的窗口：该阶段请求占窗口多数；默认只取已关闭窗口。"""
        out = []
        for w in self.snapshots():
            if only_complete and not w["complete"]:
                continue
            if w["phase_counts"].get(phase, 0) >= max(1, 0.5 * w["total"]):
                out.append(w)
        return out

    def phase_windows_containing(self, phase: str) -> list[dict]:
        """包含某阶段请求的所有窗口（不计多数、不计关闭与否）。

        用于 P3 脉冲：脉冲时长通常小于一个窗口，多数归属规则会漏判；
        429 时延/计数与窗口完整性无关。
        """
        return [w for w in self.snapshots() if w["phase_counts"].get(phase, 0) > 0]


class Judgment:
    """按合同/压测条款对平台期（P2）与脉冲期（P3）窗口做通过判定。"""

    def __init__(self, cfg):
        self.cfg = cfg

    def evaluate(self, windows: list[dict], phase: str,
                 quality_incident_count: int) -> list[dict]:
        results = []
        if phase == "platform":
            results += self._judge_capacity(windows)
            results += self._judge_ttft(windows)
            results += self._judge_otps(windows)
            results += self._judge_failure_rate(windows)
            results.append({
                "criterion": "质量四项（字符重复/工具调用重复/串台/无意义输出）",
                "target": "零确认事故",
                "actual": f"检测事故 {quality_incident_count} 起",
                "passed": quality_incident_count == 0,
            })
        elif phase == "spike":
            results += self._judge_spike_429(windows)
        return results

    def _judge_capacity(self, windows: list[dict]) -> list[dict]:
        if not windows:
            return [{"criterion": "容量稳定达到约定上限", "target": "有平台期窗口",
                     "actual": "无窗口数据", "passed": False}]
        # 目标 RPM：并发换算（设计口径：目标 = 平台期约定并发下的达成 RPM 下界）
        achieved = [w["rpm"] for w in windows]
        min_rpm = min(achieved)
        avg_rpm = sum(achieved) / len(achieved)
        target = avg_rpm * self.cfg.capacity_min_ratio
        bad = [w["window_id"] for w in windows if w["rpm"] < target]
        out = [{
            "criterion": "实际容量稳定达到约定上限（无 >10min 容量塌陷）",
            "target": f"各窗口 RPM ≥ 平台均值×{self.cfg.capacity_min_ratio:.2f}（≈{target:.0f}）",
            "actual": f"窗口数={len(windows)}, 最低 RPM={min_rpm:.0f}, 不达标窗口={bad or '无'}",
            "passed": not bad,
        }]
        if self.cfg.agreed_uncached_itpm:
            bad_itpm = [w["window_id"] for w in windows
                        if w["uncached_itpm"] < self.cfg.agreed_uncached_itpm]
            out.append({
                "criterion": "uncached ITPM ≥ 约定量",
                "target": f"≥ {self.cfg.agreed_uncached_itpm:,}",
                "actual": f"窗口最低={min(w['uncached_itpm'] for w in windows):,.0f}, "
                          f"不达标窗口={bad_itpm or '无'}",
                "passed": not bad_itpm,
            })
        return out

    def _judge_ttft(self, windows: list[dict]) -> list[dict]:
        bad = []
        for w in windows:
            for tier, t in w["ttft"].items():
                if t["n"] > 0 and not t["pass"]:
                    bad.append(f"w{w['window_id']}:{tier}(p50={t['p50']}/p90={t['p90']})")
        return [{
            "criterion": "TTFT 各 uncached 档位 P50/P90 全程达标",
            "target": "合同 TTFT 分档表（10min 窗口）",
            "actual": f"不达标: {bad[:10] or '无'}{' ...' if len(bad) > 10 else ''}",
            "passed": not bad,
        }]

    def _judge_otps(self, windows: list[dict]) -> list[dict]:
        bad = [w["window_id"] for w in windows
               if w["otps_valid"] > 0 and w["otps_violation_ratio"] > 0.01]
        return [{
            "criterion": "OTPS > 30，窗口不达标占比 ≤1%",
            "target": "合同 OTPS 条款",
            "actual": f"不达标窗口: {bad or '无'}",
            "passed": not bad,
        }]

    def _judge_failure_rate(self, windows: list[dict]) -> list[dict]:
        bad = [w["window_id"] for w in windows if w["failure_rate"] >= 0.01]
        return [{
            "criterion": "10 分钟窗口请求失败率 <1%（SLA 口径）",
            "target": "failure_rate < 0.01",
            "actual": f"不可用窗口: {bad or '无'}",
            "passed": not bad,
        }]

    def _judge_spike_429(self, windows: list[dict]) -> list[dict]:
        with_429 = [w for w in windows if w["status"]["429"] > 0]
        if not with_429:
            return [{
                "criterion": "超约定 TPM 时立即返回 429（不排队）",
                "target": "脉冲期出现 429 且时延达标",
                "actual": "脉冲期未观测到 429（供应商容量可能高于脉冲强度）",
                "passed": None,   # 无法判定，需人工解读
            }]
        p90s = [w["latency_429_p90"] for w in with_429 if w["latency_429_p90"] is not None]
        worst = max(p90s) if p90s else None
        ok = worst is not None and worst <= self.cfg.spike_429_p90_max_s
        return [{
            "criterion": "超约定 TPM 时立即返回 429（不排队）",
            "target": f"429 时延 P90 ≤ {self.cfg.spike_429_p90_max_s}s",
            "actual": f"429 窗口数={len(with_429)}, 最差 P90={worst}s",
            "passed": ok,
        }]
