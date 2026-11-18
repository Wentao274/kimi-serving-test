"""pytest 配置：CLI 选项、公共 fixtures、报告生成钩子。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from engineering.core.client import VendorClient
from engineering.core.config import Settings, from_pytest_config
from engineering.core.recorder import CaseRecord, Collector
from engineering.core.report import render_html

# 会话级单例（在 pytest_configure 中初始化）
SETTINGS: Settings | None = None
COLLECTOR: Collector | None = None


# --------------------------------------------------------------------- options
def pytest_addoption(parser):
    group = parser.getgroup("kst", "Kimi Serving Test 工程验收")
    group.addoption("--base-url", default=None, help="供应商 API base url（如 https://x/v1），或 KST_BASE_URL")
    group.addoption("--api-key", default=None, help="供应商 API key，或 KST_API_KEY")
    group.addoption("--model", default=None, help="供应商模型名，或 KST_MODEL")
    group.addoption("--official-base-url", default=None, help="官方 API base url（可选，E6 对照）")
    group.addoption("--official-api-key", default=None, help="官方 API key（可选）")
    group.addoption("--official-model", default=None, help="官方模型名（可选）")
    group.addoption("--timeout", type=float, default=None, help="单请求读超时秒数，默认 600")
    group.addoption("--include-heavy", action="store_true", help="运行重负载用例（如 #4 全量 131072 生成）")
    group.addoption("--report-dir", default=None, help="报告输出目录，默认 reports/")


def pytest_configure(config):
    global SETTINGS, COLLECTOR
    SETTINGS = from_pytest_config(config)
    COLLECTOR = Collector()
    config.addinivalue_line("markers", "heavy: 重负载用例，需 --include-heavy 才运行")


# -------------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def settings() -> Settings:
    assert SETTINGS is not None
    return SETTINGS


@pytest.fixture(scope="session")
def client(settings) -> VendorClient:
    problems = settings.validate()
    if problems:
        pytest.fail("配置不完整：\n  - " + "\n  - ".join(problems), pytrace=False)
    return VendorClient(settings.base_url, settings.api_key, settings.model, settings.timeout)


@pytest.fixture(scope="session")
def official_client(settings) -> VendorClient | None:
    if not settings.has_official:
        return None
    return VendorClient(settings.official_base_url, settings.official_api_key,
                        settings.official_model, settings.timeout)


@pytest.fixture(scope="session")
def collector() -> Collector:
    assert COLLECTOR is not None
    return COLLECTOR


@pytest.fixture
def rec(request, collector) -> CaseRecord:
    """每个测试函数一个 CaseRecord；测试结束后自动入库。"""
    node = request.node
    module = node.module.__name__ if node.module else "unknown"
    param_id = node.callspec.id if hasattr(node, "callspec") else ""
    doc = (node.function.__doc__ or "").strip().splitlines()
    title = node.originalname or node.name
    if param_id:
        title = f"{title} [{param_id}]"
    record = CaseRecord(
        suite=module,
        case_id=node.nodeid,
        title=title,
        description=doc[0] if doc else "",
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    node._case_record = record
    yield record
    collector.add(record)


# ----------------------------------------------------------------------- hooks
@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    record: CaseRecord | None = getattr(item, "_case_record", None)
    if record is None:
        if report.when == "setup" and report.skipped:
            # 对 skip 的用例也登记一条记录，保证报告完整
            record = CaseRecord(
                suite=item.module.__name__ if item.module else "unknown",
                case_id=item.nodeid,
                title=item.name,
                outcome="skipped",
                error=str(report.longrepr)[:2000] if report.longrepr else "",
                started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            item._pending_skip_record = record
        return
    if report.when == "call" or (report.when == "setup" and report.failed):
        if report.failed:
            record.outcome = "error" if report.when == "setup" else "failed"
            record.error = str(report.longrepr)[:8000]
        elif report.skipped:
            record.outcome = "skipped"
            if report.longrepr:
                record.error = str(report.longrepr)[:2000]
    return report


def pytest_sessionfinish(session, exitstatus):
    global COLLECTOR, SETTINGS
    collector, settings = COLLECTOR, SETTINGS
    if collector is None:
        return
    if session.config.option.collectonly or not collector.records:
        return
    # 登记 setup 阶段 skip 的用例
    for item in getattr(session, "items", []):
        pending = getattr(item, "_pending_skip_record", None)
        if pending is not None and not any(r.case_id == pending.case_id for r in collector.records):
            collector.add(pending)
    collector.finish()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(settings.report_dir if settings else "reports") / f"engineering_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    data_path = out_dir / "report_data.json"
    # 报告命名：<model>_report_<yyyymmddhhmmss>.html（具备识别性）
    safe_model = "".join(c if (c.isalnum() or c in "._-") else "_" for c in (settings.model if settings else "model"))
    file_stamp = stamp.replace("_", "")
    html_path = out_dir / f"{safe_model}_report_{file_stamp}.html"

    meta = {
        "模型": settings.model if settings else "?",
        "Endpoint": settings.base_url if settings else "?",
        "开始时间": collector.started_at,
        "结束时间": collector.finished_at,
        "含重负载用例": "是" if (settings and settings.include_heavy) else "否",
    }

    payload = collector.to_dict()
    payload["meta"] = meta
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(collector, meta), encoding="utf-8")

    summary = collector.summary()
    print("\n" + "=" * 70)
    print(f"工程验收报告已生成：")
    print(f"  HTML : {html_path}")
    print(f"  JSON : {data_path}")
    print(f"  汇总 : 共 {summary['total']} 例 | 通过 {summary['passed']} | "
          f"失败 {summary['failed']} | 错误 {summary['error']} | "
          f"跳过 {summary['skipped']} | 软性警告 {summary['soft_warnings']}")
    print("=" * 70)
