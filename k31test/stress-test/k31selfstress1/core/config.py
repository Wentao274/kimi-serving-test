"""配置加载：config.yaml 为唯一参数源，CLI 覆盖常用项（CLI > yaml）。

阈值（baselines/tpot_limits/hit_rate_limit 等）只在 yaml 维护，不提供 CLI 覆盖，
避免临时改判据。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_tests.py k31selfstress1",
        description="Kimi-K3.1-Pro 性能基线测试（TTFT/TPOT/缓存，三场景合一报告）")
    p.add_argument("--base-url", default=os.environ.get("KST_BASE_URL"), help="供应商 API base url")
    p.add_argument("--api-key", default=os.environ.get("KST_API_KEY"), help="供应商 API key")
    p.add_argument("--model", default=None, help="被测模型名（覆盖 config.yaml）")
    p.add_argument("--config", default=None, help="自定义 config.yaml 路径")
    p.add_argument("--scenario", choices=["all", "ttft", "cache"], default=None,
                   help="运行场景（默认 all）")
    p.add_argument("--concurrency", type=int, default=None, help="TTFT/TPOT 并发数")
    p.add_argument("--samples-per-tier", type=int, default=None, help="TTFT 每档请求数")
    p.add_argument("--quick", action="store_true", help="Checklist 口径：16k/64k/100k × quick_samples")
    p.add_argument("--cache-rounds", type=int, default=None, help="缓存命中率轮次")
    p.add_argument("--ttl-rounds", type=int, default=None, help="TTL 轮次")
    p.add_argument("--ttl-wait-s", type=float, default=None, help="TTL 探测等待秒数")
    p.add_argument("--ttl-expire-probe-s", type=float, default=None,
                   help="过期观察点秒数（0=关闭）")
    p.add_argument("--timeout", type=float, default=None, help="单请求读超时秒数")
    p.add_argument("--report-dir", default=None, help="报告根目录（默认 reports）")
    return p


def load_config(args: argparse.Namespace) -> dict:
    path = Path(args.config) if args.config else _DEFAULT_CONFIG
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["_config_path"] = str(path)

    # CLI 覆盖（仅常用项；阈值不可覆盖）
    if args.model:
        cfg["model"] = args.model
    if args.timeout is not None:
        cfg["timeout_s"] = args.timeout
    tt = cfg["ttft_tpot"]
    if args.scenario:
        tt["enabled"] = args.scenario in ("all", "ttft")
        cfg["cache"]["enabled"] = args.scenario in ("all", "cache")
    if args.concurrency is not None:
        tt["concurrency"] = args.concurrency
    if args.samples_per_tier is not None:
        tt["samples_per_tier"] = args.samples_per_tier
    if args.quick:
        tt["quick_mode"] = True
    cc = cfg["cache"]
    if args.cache_rounds is not None:
        cc["hit_rate_rounds"] = args.cache_rounds
    if args.ttl_rounds is not None:
        cc["ttl_rounds"] = args.ttl_rounds
    if args.ttl_wait_s is not None:
        cc["ttl_wait_s"] = args.ttl_wait_s
    if args.ttl_expire_probe_s is not None:
        cc["ttl_expire_probe_s"] = args.ttl_expire_probe_s
    if args.report_dir:
        cfg["report"]["base_dir"] = args.report_dir

    # 连接信息（仅 CLI/环境变量）
    cfg["base_url"] = (args.base_url or "").rstrip("/")
    cfg["api_key"] = args.api_key or ""
    return cfg


def validate(cfg: dict) -> list[str]:
    problems = []
    if not cfg.get("base_url"):
        problems.append("缺少 --base-url（或 KST_BASE_URL）")
    if not cfg.get("api_key"):
        problems.append("缺少 --api-key（或 KST_API_KEY）")
    if not cfg.get("model"):
        problems.append("缺少模型名（--model 或 config.yaml model）")
    return problems
