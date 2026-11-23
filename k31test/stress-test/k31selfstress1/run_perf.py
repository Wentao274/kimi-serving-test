"""k31selfstress1 CLI 入口：python run_tests.py k31selfstress1 [参数...]

场景：TTFT+TPOT（scenario_ttft，同一脚本）→ 缓存基线（scenario_cache）→
三场景合一报告：reports/k31selfstress1/<时间戳>/<model>_selfstress1_report_<时间戳>.html
+ summary.json + metrics.jsonl。退出码：任一判定 FAIL → 1。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from k31selfstress1.core.config import build_parser, load_config, validate
from k31selfstress1.core.client import PerfClient
from k31selfstress1.core import report as report_mod
from k31selfstress1.core import scenario_cache, scenario_ttft


def _log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


async def _run(cfg: dict) -> tuple[dict | None, dict | None, str]:
    client = PerfClient(cfg["base_url"], cfg["api_key"], cfg["model"], cfg["timeout_s"])
    ttft_result = None
    cache_result = None
    if cfg["ttft_tpot"].get("enabled"):
        ttft_result = await scenario_ttft.run(client, cfg, _log)
    if cfg["cache"].get("enabled"):
        cache_result = await scenario_cache.run(client, cfg, _log)
    return ttft_result, cache_result, client.deploy_id


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args)
    problems = validate(cfg)
    if problems:
        print("配置不完整：\n  - " + "\n  - ".join(problems))
        return 2

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(cfg["report"]["base_dir"]) / "k31selfstress1" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"K3.1-Pro 性能基线 | model={cfg['model']} | "
          f"mode={'quick' if cfg['ttft_tpot'].get('quick_mode') else 'full'} | "
          f"config={cfg['_config_path']}")
    print(f"场景：TTFT/TPOT={'开' if cfg['ttft_tpot'].get('enabled') else '关'} "
          f"缓存={'开' if cfg['cache'].get('enabled') else '关'} | 输出目录: {out_dir}")
    print("=" * 72)

    t0 = time.perf_counter()
    ttft_result, cache_result, deploy_id = asyncio.run(_run(cfg))
    elapsed = time.perf_counter() - t0

    html_path, summary = report_mod.render(out_dir, cfg, ttft_result, cache_result,
                                           started, elapsed, deploy_id)

    n_fail = 0
    if ttft_result:
        n_fail += sum(1 for t in ttft_result["tiers"] if not t["passed"])
        n_fail += 0 if ttft_result["tpot"]["passed"] else 1
    if cache_result:
        n_fail += 0 if cache_result["hit_rate"]["passed"] else 1
        n_fail += 0 if cache_result["ttl"]["passed"] else 1

    print("\n" + "=" * 72)
    print(f"性能基线报告: {html_path}")
    print(f"判定: 失败 {n_fail} 项 | 总请求 {summary['stats']['total']} | "
          f"总判定 {'PASS' if summary['result'] == 'PASS' else 'FAIL'}")
    print("=" * 72)
    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
