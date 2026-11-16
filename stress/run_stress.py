"""压力测试 CLI 入口：python run_tests.py stress [参数...]

阶段：baseline(P0 基线) / ramp(P1 爬坡) / platform(P2 平台) / spike(P3 脉冲) / full(全流程)。
产出：<report_dir>/stress_<时间戳>/ 下 report.html、summary.json、windows.json、
metrics.jsonl（逐请求指标，无原始请求/响应，符合闭源数据合规）、quality_incidents.json。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .core.config import build_config
from .core.generator import StressEngine
from .core.report import write_outputs


def main(argv: list[str]) -> int:
    cfg = build_config(argv)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_name = f"stress_{stamp}"
    run_dir = Path(cfg.report_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"K3.1 压力测试 | phase={cfg.phase} | model={cfg.model}")
    print(f"约定并发={cfg.agreed_concurrency} 约定TPM={cfg.agreed_tpm:,} "
          f"uncached_ITPM={cfg.agreed_uncached_itpm or '不判定'} "
          f"负载阈值TPM={cfg.effective_load_threshold:,}")
    print(f"输出目录: {run_dir}")
    print("=" * 72)

    engine = StressEngine(cfg, run_dir)
    results = asyncio.run(engine.run())
    summary = write_outputs(cfg, results, run_dir, run_name)

    judged = [j for items in results["judgments"].values() for j in items]
    n_fail = sum(1 for j in judged if j["passed"] is False)
    n_na = sum(1 for j in judged if j["passed"] is None)
    print("\n" + "=" * 72)
    print(f"压测报告: {run_dir / 'report.html'}")
    print(f"判定: 失败 {n_fail} 项 | 无法判定 {n_na} 项 | "
          f"质量事故 {len(results['quality_incidents'])} 起 | 总请求 {results['total_requests']}")
    print("=" * 72)
    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
