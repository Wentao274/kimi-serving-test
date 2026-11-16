"""测试数据加载工具。"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

IMAGE_CASES_FILE = "vendor-img-testcases-inhouse-3.jsonl"
OPENCLAW_CASES_FILE = "9.openclaw_cases12.jsonl"


def load_jsonl(name: str) -> list[dict]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_image_cases() -> list[dict]:
    """25 条图片用例：每行 {"expected_finish_reason", "transformed_request"}。"""
    return load_jsonl(IMAGE_CASES_FILE)


def load_openclaw_cases() -> list[dict]:
    """12 条 OpenClaw 用例：每行 {"line", "request"}。"""
    return load_jsonl(OPENCLAW_CASES_FILE)
