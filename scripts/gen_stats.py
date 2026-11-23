#!/usr/bin/env python
"""从报告产物生成 stats.properties（供 Jenkins 邮件统计）。

用法：
    python scripts/gen_stats.py <out_dir> <suite> <exit_code>

- engineering / k31selfcheck1 / k31selfcheck2：读取 <out_dir>/<suite>_*/report_data.json（取最新）的 summary；
- stress：读取 <out_dir>/stress_*/summary.json（取最新）的判定结果；
- RESULT 以测试进程退出码为准（0=PASS，非 0=FAIL）。
"""

from __future__ import annotations

import glob
import json
import os
import sys


def latest(pattern: str) -> str | None:
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def stats_engineering(out_dir: str, suite: str = "engineering") -> dict:
    path = latest(os.path.join(out_dir, f"{suite}_*", "report_data.json"))
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)["summary"]
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    rate = round(passed / total * 100, 2) if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": summary.get("failed", 0),
        "skipped": summary.get("skipped", 0),
        "errors": summary.get("error", 0),
        "rate": rate,
    }


def stats_stress(out_dir: str) -> dict:
    path = latest(os.path.join(out_dir, "stress_*", "summary.json"))
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    judged = [j for items in summary.get("judgments", {}).values() for j in items]
    failed = sum(1 for j in judged if j.get("passed") is False)
    passed = sum(1 for j in judged if j.get("passed") is True)
    total_j = len(judged)
    rate = round(passed / total_j * 100, 2) if total_j else 0.0
    return {
        "total": summary.get("total_requests", 0),
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "errors": summary.get("quality_incident_count", 0),
        "rate": rate,
    }


def main() -> int:
    out_dir, suite, exit_code = sys.argv[1], sys.argv[2], int(sys.argv[3])
    stats = stats_stress(out_dir) if suite == "stress" else stats_engineering(out_dir, suite)
    stats["result"] = "PASS" if exit_code == 0 else "FAIL"
    stats["suite"] = suite

    props = os.path.join(out_dir, "stats.properties")
    with open(props, "w", encoding="utf-8") as f:
        for k, v in stats.items():
            f.write(f"{k}={v}\n")
    print(f"[gen_stats] {props}: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
