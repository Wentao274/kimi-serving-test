"""阶段引擎：P0 基线 → P1 爬坡 → P2 平台 → P3 脉冲。

- 异步 worker 池按阶段并发数伸缩；
- 逐请求指标即时聚合 + JSONL 落盘（仅指标，不落原始请求/响应，合规）；
- 窗口关闭即快照 windows.json（长时运行中断不丢聚合结果）；
- 质量四项即时检测，事故截断记录。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from .async_client import AsyncVendorClient, RequestOutcome
from .config import StressConfig
from .metrics import Aggregator, Judgment, RequestMetric
from .quality import (CanaryRegistry, QualityIncident, check_char_repetition,
                      check_nonsense, check_toolcall_repetition)
from .scenarios import TrafficBuilder
from .contract import TIER_NAMES


class MetricsWriter:
    def __init__(self, path: Path, flush_every: int = 100):
        self._fh = path.open("a", encoding="utf-8")
        self._n = 0
        self._flush_every = flush_every

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._n += 1
        if self._n % self._flush_every == 0:
            self._fh.flush()

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()


class StressEngine:
    def __init__(self, cfg: StressConfig, run_dir: Path):
        self.cfg = cfg
        self.run_dir = run_dir
        self.run_start = time.time()
        self.aggregator = Aggregator(self.run_start, cfg.window_s,
                                     cfg.effective_load_threshold)
        self.canaries = CanaryRegistry()
        self.client = AsyncVendorClient(cfg.base_url, cfg.api_key, cfg.timeout,
                                        max_connections=max(cfg.spike_concurrency,
                                                            cfg.agreed_concurrency) * 2 + 64)
        image_urls = cfg.image_urls or None
        if image_urls is None:
            from .scenarios import default_image_urls
            image_urls = default_image_urls()
        self.traffic = TrafficBuilder(
            model=cfg.model, scenario_mix=cfg.scenario_mix, tier_mix=cfg.tier_mix,
            prompt_scale=cfg.prompt_scale, shared_prefix_pool=cfg.shared_prefix_pool,
            image_urls=image_urls)
        self.judgment = Judgment(cfg)
        self.metrics_writer = MetricsWriter(run_dir / "metrics.jsonl")
        self._phase_stop = asyncio.Event()
        self._tpm_window: list[tuple[float, int]] = []   # 滚动 60s TPM 估算（负载阈值口径）
        self.phase_judgments: dict[str, list[dict]] = {}
        self.baseline_results: list[dict] = []

    # ------------------------------------------------------------------ 工具
    def _current_tpm(self) -> float:
        now = time.time()
        cutoff = now - 60.0
        self._tpm_window = [(t, v) for t, v in self._tpm_window if t >= cutoff]
        return sum(v for _, v in self._tpm_window)

    def _record_tpm(self, m: RequestMetric) -> None:
        if m.uncached_tokens is not None:
            self._tpm_window.append((m.ts, m.uncached_tokens + (m.completion_tokens or 0)))

    def _quality_check(self, session_id: str, outcome: RequestOutcome) -> list[str]:
        """需求文档压测条款质量四项检测（finish_reason 不作质量判据，
        其分布保留在 metrics.jsonl 供离线分析）。"""
        flags = []
        detail = check_char_repetition(outcome.text)
        if detail:
            flags.append("char_repetition")
            self.aggregator.add_incident(QualityIncident("char_repetition", session_id,
                                                         outcome.started_ts, detail))
        detail = check_toolcall_repetition(outcome.tool_calls)
        if detail:
            flags.append("toolcall_repetition")
            self.aggregator.add_incident(QualityIncident("toolcall_repetition", session_id,
                                                         outcome.started_ts, detail))
        foreign = self.canaries.foreign_canary_in(outcome.text, session_id)
        if foreign:
            flags.append("crosstalk")
            self.aggregator.add_incident(QualityIncident(
                "crosstalk", session_id, outcome.started_ts,
                f"响应中出现其他会话 canary: {foreign}"))
        detail = check_nonsense(outcome.finish_reason, outcome.text, len(outcome.tool_calls))
        if detail:
            flags.append("nonsense")
            self.aggregator.add_incident(QualityIncident("nonsense", session_id,
                                                         outcome.started_ts, detail))
        return flags

    async def _fire(self, session_id: str, scenario: str, tier: str,
                    payload: dict, phase: str) -> None:
        outcome = await self.client.stream_chat(payload)
        flags = self._quality_check(session_id, outcome)
        m = RequestMetric(
            ts=outcome.started_ts, phase=phase, session_id=session_id,
            scenario=scenario, tier=tier, status=outcome.status,
            ttft_s=outcome.ttft_s, gen_s=outcome.gen_s, total_s=outcome.total_s,
            otps=outcome.otps, prompt_tokens=outcome.prompt_tokens,
            cached_tokens=outcome.cached_tokens,
            completion_tokens=outcome.completion_tokens,
            uncached_tokens=outcome.uncached_tokens,
            finish_reason=outcome.finish_reason, failure=False,
            quality_flags=flags,
        )
        self._record_tpm(m)
        self.aggregator.add(m, phase_tpm_now=self._current_tpm())
        self.metrics_writer.write(m.to_dict())

    # ------------------------------------------------------------------ worker
    async def _worker(self, worker_id: int, phase: str, stop: asyncio.Event) -> None:
        session_id = f"{phase}-w{worker_id}-{uuid.uuid4().hex[:6]}"
        canary = self.canaries.register(session_id)
        while not stop.is_set():
            scenario, tier, cacheable = self.traffic.pick()
            payload = self.traffic.build(scenario, tier, canary, cacheable)
            try:
                await self._fire(session_id, scenario, tier, payload, phase)
            except Exception as exc:  # 兜底：单请求异常不中断压测
                self.aggregator.add_incident(QualityIncident(
                    "harness_error", session_id, time.time(), f"{type(exc).__name__}: {exc}"))
            if self.cfg.think_time_s:
                await asyncio.sleep(self.cfg.think_time_s)

    async def _run_stage(self, phase: str, duration_s: float, concurrency: int) -> None:
        stop = asyncio.Event()
        workers = [asyncio.create_task(self._worker(i, phase, stop))
                   for i in range(concurrency)]
        print(f"  [{phase}] 并发 {concurrency}，时长 {duration_s}s ...", flush=True)
        t0 = time.time()
        while time.time() - t0 < duration_s:
            await asyncio.sleep(min(5.0, max(duration_s - (time.time() - t0), 0.1)))
            self._write_windows_snapshot()
        stop.set()
        await asyncio.gather(*workers, return_exceptions=True)
        self._write_windows_snapshot()
        done = self.aggregator.total_requests
        print(f"  [{phase}] 完成，累计请求 {done}", flush=True)

    def _write_windows_snapshot(self) -> None:
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": self.aggregator.total_requests,
            "windows": self.aggregator.snapshots(),
        }
        (self.run_dir / "windows.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _windows_of_phase(self, phase: str) -> list[dict]:
        """归属某阶段的已关闭窗口（阶段请求占多数者），不含未关闭的边界窗口。"""
        return self.aggregator.phase_windows(phase, only_complete=True)

    # ------------------------------------------------------------------ 阶段
    async def phase_baseline(self) -> None:
        """P0：各 TTFT 档位 uncached 探针基线（真实档位测量 + 连通性预检）。"""
        print("[P0] 基线校准：各档位 uncached 探针 ...", flush=True)
        for tier in TIER_NAMES:
            for i in range(self.cfg.baseline_probes_per_tier):
                session_id = f"baseline-{tier}-{i}"
                canary = self.canaries.register(session_id)
                payload = self.traffic.probe(tier, canary)
                await self._fire(session_id, "text_chat", tier, payload, "baseline")
        # 基线汇总
        snaps = [w for w in self.aggregator.snapshots()]
        for w in snaps:
            for tier, t in w["ttft"].items():
                if t["n"] > 0:
                    self.baseline_results.append({
                        "tier": tier, "n": t["n"], "p50": t["p50"], "p90": t["p90"],
                        "p50_max": t["p50_max"], "p90_max": t["p90_max"], "pass": t["pass"],
                    })
        self._write_windows_snapshot()

    async def phase_ramp(self) -> None:
        """P1：阶梯爬坡（1000 RPM / 25M TPM 起步 → 约定并发/TPM）。"""
        print("[P1] 爬坡 ...", flush=True)
        for stage in self.cfg.ramp_stages:
            await self._run_stage(f"ramp-{stage.name}", stage.duration_s, stage.concurrency)

    async def phase_platform(self) -> None:
        """P2：约定并发平台期（默认 24h），结束后按合同口径判定。"""
        print(f"[P2] 平台期：并发 {self.cfg.agreed_concurrency}，"
              f"时长 {self.cfg.platform_duration_s}s ...", flush=True)
        await self._run_stage("platform", self.cfg.platform_duration_s,
                              self.cfg.agreed_concurrency)
        windows = self._windows_of_phase("platform")
        quality_n = len(self.aggregator.quality_incidents)
        self.phase_judgments["platform"] = self.judgment.evaluate(
            windows, "platform", quality_n)

    async def phase_spike(self) -> None:
        """P3：超约定 TPM 脉冲，验证立即 429。"""
        print(f"[P3] 脉冲：并发 {self.cfg.spike_concurrency} "
              f"(约定 {self.cfg.agreed_concurrency})，{self.cfg.spike_duration_s}s ...", flush=True)
        await self._run_stage("spike", self.cfg.spike_duration_s,
                              self.cfg.spike_concurrency)
        # 脉冲短于窗口：用"包含脉冲请求"的窗口（429 时延与窗口完整性无关）
        windows = self.aggregator.phase_windows_containing("spike")
        self.phase_judgments["spike"] = self.judgment.evaluate(windows, "spike", 0)

    async def run(self) -> dict:
        phases = {
            "baseline": [self.phase_baseline],
            "ramp": [self.phase_ramp],
            "platform": [self.phase_platform],
            "spike": [self.phase_spike],
            "full": [self.phase_baseline, self.phase_ramp,
                     self.phase_platform, self.phase_spike],
        }[self.cfg.phase]
        try:
            for fn in phases:
                await fn()
        finally:
            self.metrics_writer.close()
            await self.client.aclose()
            self._write_windows_snapshot()
        return {
            "baseline": self.baseline_results,
            "judgments": self.phase_judgments,
            "quality_incidents": [vars(i) for i in self.aggregator.quality_incidents],
            "windows": self.aggregator.snapshots(),
            "total_requests": self.aggregator.total_requests,
        }
