"""压力测试配置：CLI 参数解析。

环境变量回退：KST_BASE_URL / KST_API_KEY / KST_MODEL。
约定量（--agreed-*）对应压力测试条款的"约定量"，执行前需与 Kimi 团队确认。
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field


@dataclass
class StageSpec:
    name: str
    duration_s: float
    concurrency: int


@dataclass
class StressConfig:
    # 被测端
    base_url: str
    api_key: str
    model: str
    timeout: float = 600.0

    # 约定量（压力测试条款：并发量/总 TPM/uncached ITPM ≥ 约定量）
    agreed_concurrency: int = 50
    agreed_tpm: int = 100_000_000
    agreed_uncached_itpm: int = 0          # 0 = 未约定（不参与判定）
    load_threshold_tpm: int = 0            # 负载阈值（7天峰值平均的代入口径）；0 = 用 agreed_tpm

    # 阶段
    phase: str = "full"                    # baseline / ramp / platform / spike / full
    ramp_stages: list[StageSpec] = field(default_factory=list)
    platform_duration_s: float = 24 * 3600
    spike_duration_s: float = 120.0
    spike_concurrency: int = 100
    baseline_probes_per_tier: int = 2
    think_time_s: float = 0.0              # worker 请求间隔（0 = 最大压力）

    # 流量模型
    prompt_scale: float = 1.0              # prompt 长度缩放（demo 用小值）
    scenario_mix: dict = field(default_factory=lambda: {
        "text_chat": 0.5, "image_chat": 0.2, "text_claw": 0.2, "image_claw": 0.1})
    tier_mix: dict = field(default_factory=lambda: {
        "<8k": 0.50, "8k-32k": 0.25, "32k-128k": 0.15, "128k-256k": 0.07, "256k-1m": 0.03})
    shared_prefix_pool: int = 20           # 共享前缀池大小（构造 cache 命中）
    image_urls: list[str] = field(default_factory=list)

    # 聚合与判定
    window_s: int = 600                    # 合同口径 600s；demo 可调小
    otps_min: float = 30.0
    spike_429_p90_max_s: float = 5.0
    capacity_min_ratio: float = 0.95

    # 数据合规（闭源测试：默认只留聚合指标与截断样本）
    sample_text_rate: float = 0.01         # 响应文本采样率（截断 300 字符，供无意义输出人工复核）
    sample_text_max_chars: int = 300

    # 输出
    report_dir: str = "reports"

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def effective_load_threshold(self) -> int:
        return self.load_threshold_tpm or self.agreed_tpm


def _parse_stages(spec: str) -> list[StageSpec]:
    """解析 'warmup:60:4,climb:120:16' → [StageSpec(name, duration_s, concurrency)]"""
    stages = []
    for part in spec.split(","):
        name, dur, conc = part.strip().split(":")
        stages.append(StageSpec(name=name, duration_s=float(dur), concurrency=int(conc)))
    return stages


def build_config(argv: list[str]) -> StressConfig:
    p = argparse.ArgumentParser(
        prog="run_tests.py stress",
        description="K3.1 压力测试（按客户需求文档合同指标执行）")
    p.add_argument("--base-url", default=os.environ.get("KST_BASE_URL", ""))
    p.add_argument("--api-key", default=os.environ.get("KST_API_KEY", ""))
    p.add_argument("--model", default=os.environ.get("KST_MODEL", ""))
    p.add_argument("--timeout", type=float, default=600.0)

    p.add_argument("--agreed-concurrency", type=int, default=50,
                   help="约定并发量（测试期 ≥50）")
    p.add_argument("--agreed-tpm", type=int, default=100_000_000,
                   help="约定总 TPM（测试期 ≥100M）")
    p.add_argument("--agreed-uncached-itpm", type=int, default=0,
                   help="约定 uncached ITPM；0=不判定")
    p.add_argument("--load-threshold-tpm", type=int, default=0,
                   help="负载阈值（7天每分钟峰值平均的代入口径）；默认=agreed-tpm")

    p.add_argument("--phase", default="full",
                   choices=["baseline", "ramp", "platform", "spike", "full"],
                   help="执行阶段；full = P0基线→P1爬坡→P2平台→P3脉冲")
    p.add_argument("--ramp-stages", default="",
                   help="爬坡阶梯，如 'start:900:10,climb:900:30,peak:900:50'（名称:秒:并发）")
    p.add_argument("--platform-duration", type=float, default=24 * 3600,
                   help="P2 平台期秒数（默认 24h）")
    p.add_argument("--spike-duration", type=float, default=120.0)
    p.add_argument("--spike-concurrency", type=int, default=0,
                   help="P3 脉冲并发（默认 = 约定并发 × 2）")
    p.add_argument("--baseline-probes-per-tier", type=int, default=2)
    p.add_argument("--think-time", type=float, default=0.0)

    p.add_argument("--prompt-scale", type=float, default=1.0,
                   help="prompt 长度缩放（demo 用 0.01 级）")
    p.add_argument("--shared-prefix-pool", type=int, default=20)
    p.add_argument("--image-url", action="append", dest="image_urls", default=[],
                   help="图片 URL（可多次指定）；缺省从工程验收图片用例中提取")

    p.add_argument("--window-s", type=int, default=600,
                   help="聚合窗口秒数（合同口径 600；demo 可调小）")
    p.add_argument("--otps-min", type=float, default=30.0)
    p.add_argument("--spike-429-p90-max-s", type=float, default=5.0,
                   help="P3 脉冲期 429 响应时延 P90 上限（默认 5s）")
    p.add_argument("--capacity-min-ratio", type=float, default=0.95,
                   help="平台期窗口达成 RPM / 目标 RPM 之比下限（默认 0.95）")

    p.add_argument("--sample-text-rate", type=float, default=0.01)
    p.add_argument("--report-dir", default="reports")
    p.add_argument("--run-name", default="",
                   help="运行目录名后缀（默认自动时间戳）")

    args = p.parse_args(argv)

    if not args.base_url or not args.api_key or not args.model:
        p.error("缺少 --base-url / --api-key / --model（或 KST_* 环境变量）")

    ramp = _parse_stages(args.ramp_stages) if args.ramp_stages else [
        StageSpec("start", 900, max(1, args.agreed_concurrency // 5)),
        StageSpec("climb", 900, max(1, args.agreed_concurrency // 2)),
        StageSpec("peak", 900, args.agreed_concurrency),
    ]

    return StressConfig(
        base_url=args.base_url, api_key=args.api_key, model=args.model,
        timeout=args.timeout,
        agreed_concurrency=args.agreed_concurrency,
        agreed_tpm=args.agreed_tpm,
        agreed_uncached_itpm=args.agreed_uncached_itpm,
        load_threshold_tpm=args.load_threshold_tpm,
        phase=args.phase,
        ramp_stages=ramp,
        platform_duration_s=args.platform_duration,
        spike_duration_s=args.spike_duration,
        spike_concurrency=args.spike_concurrency or args.agreed_concurrency * 2,
        baseline_probes_per_tier=args.baseline_probes_per_tier,
        think_time_s=args.think_time,
        prompt_scale=args.prompt_scale,
        shared_prefix_pool=args.shared_prefix_pool,
        image_urls=args.image_urls,
        window_s=args.window_s,
        otps_min=args.otps_min,
        spike_429_p90_max_s=args.spike_429_p90_max_s,
        capacity_min_ratio=args.capacity_min_ratio,
        sample_text_rate=args.sample_text_rate,
        report_dir=args.report_dir,
    )
