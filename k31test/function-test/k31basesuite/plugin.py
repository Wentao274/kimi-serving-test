"""k31test/function-test 共享 pytest 框架（插件形式，经 run_tests.py 以 -p 注入）。

为 k31selfcheck1 / k31selfcheck2 / k31basesuite 提供统一的：
- 命令行选项注册（--base-url/--api-key/--model/--official-*/--timeout/--include-heavy/--report-dir）
- 共享 fixtures：settings / client / official_client / collector / rec
- 单一 Collector 与报告写出：按环境变量 KST_ACTIVE_SUITE 决定报告目录名、
  文件名与标题（各套件运行产出各自报告，公共用例照常计入）。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from engineering.core.client import VendorClient
from engineering.core.config import Settings, from_pytest_config
from engineering.core.recorder import CaseRecord, Collector
from engineering.core.report import render_html
from k31basesuite.module_titles import titles_for

SETTINGS: Settings | None = None
COLLECTOR: Collector | None = None

# 套件报告元信息：目录名 / 报告文件标识 / 标题
SUITE_META = {
    "k31selfcheck1": {
        "title": "K3.1-Pro 供应商自测基线（功能兼容性）",
        "file_tag": "selfcheck1_report",
        "protocol_list": True,   # 报告 meta 含三协议支持清单（依据 k01 探测）
    },
    "k31selfcheck2": {
        "title": "模型接入要求（对外版）功能测试（3.1/3.2）",
        "file_tag": "selfcheck2_report",
        "protocol_list": False,
    },
    "k31selfcheck3": {
        "title": "K3.1 功能与兼容性测试（指令遵循/孤儿tool/一致性/知识库/安全围栏/超时异常）",
        "file_tag": "selfcheck3_report",
        "protocol_list": False,
    },
    "k31basesuite": {
        "title": "K3.1 公共基础用例集（k31basesuite）",
        "file_tag": "basesuite_report",
        "protocol_list": False,
    },
}


def _active_suite() -> str:
    suite = os.environ.get("KST_ACTIVE_SUITE", "k31basesuite")
    return suite if suite in SUITE_META else "k31basesuite"


def pytest_addoption(parser):
    group = parser.getgroup("k31basesuite", "K3.1 功能测试共享框架（function-test）")
    group.addoption("--base-url", default=None, help="供应商 API base url，或 KST_BASE_URL")
    group.addoption("--api-key", default=None, help="供应商 API key，或 KST_API_KEY")
    group.addoption("--model", default=None, help="被测模型名，或 KST_MODEL")
    group.addoption("--official-base-url", default=None, help="官方 API base url（可选，对照用）")
    group.addoption("--official-api-key", default=None, help="官方 API key（可选）")
    group.addoption("--official-model", default=None, help="官方模型名（可选）")
    group.addoption("--timeout", type=float, default=None, help="单请求读超时秒数，默认 600")
    group.addoption("--include-heavy", action="store_true", help="运行重负载用例")
    group.addoption("--report-dir", default=None, help="报告输出目录，默认 reports/")


def pytest_configure(config):
    global SETTINGS, COLLECTOR
    SETTINGS = from_pytest_config(config)
    COLLECTOR = Collector()
    config.addinivalue_line("markers", "heavy: 重负载用例，需 --include-heavy 才运行")


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


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    record: CaseRecord | None = getattr(item, "_case_record", None)
    if record is None:
        if report.when == "setup" and report.skipped:
            record = CaseRecord(
                suite=item.module.__name__ if item.module else "unknown",
                case_id=item.nodeid,
                title=item.name,
                outcome="skipped",
                error=str(report.longrepr)[:2000] if report.longrepr else "",
                started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            item._pending_skip_record = record
        return report
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
    for item in getattr(session, "items", []):
        pending = getattr(item, "_pending_skip_record", None)
        if pending is not None and not any(r.case_id == pending.case_id for r in collector.records):
            collector.add(pending)
    collector.finish()

    suite = _active_suite()
    smeta = SUITE_META[suite]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(settings.report_dir if settings else "reports") / suite / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    data_path = out_dir / "report_data.json"
    safe_model = "".join(c if (c.isalnum() or c in "._-") else "_"
                         for c in (settings.model if settings else "model"))
    html_path = out_dir / f"{safe_model}_{smeta['file_tag']}_{stamp.replace('_', '')}.html"

    # 部署版本（若响应头含 X-Msh-ProviderDeployId 则记录）
    deploy_id = ""
    for r in collector.records:
        headers = (r.extra or {}).get("response_headers") or {}
        deploy_id = headers.get("x-msh-providerdeployid", "")
        if deploy_id:
            break

    meta = {
        "模型": settings.model if settings else "?",
        "部署版本": deploy_id or "（响应头未返回 X-Msh-ProviderDeployId）",
        "Endpoint": settings.base_url if settings else "?",
        "开始时间": collector.started_at,
        "结束时间": collector.finished_at,
        "含重负载用例": "是" if (settings and settings.include_heavy) else "否",
    }
    if smeta.get("protocol_list"):
        proto_support = {"Chat": "未测"}
        for r in collector.records:
            cid = r.case_id
            if "test_k01_chat" in cid:
                proto_support["Chat"] = "开放" if r.outcome == "passed" else f"异常({r.outcome})"
            elif "test_k01_responses" in cid:
                proto_support["Responses"] = "开放" if r.outcome == "passed" else f"未开放/异常({r.outcome})"
            elif "test_k01_messages" in cid:
                proto_support["Messages"] = "开放" if r.outcome == "passed" else f"未开放/异常({r.outcome})"
        meta["协议支持清单"] = "；".join(f"{k}: {v}" for k, v in proto_support.items())

    payload = collector.to_dict()
    payload["meta"] = meta
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(collector, meta, module_titles=titles_for(suite)),
                         encoding="utf-8")

    summary = collector.summary()
    print("\n" + "=" * 70)
    print(f"{smeta['title']} 报告已生成：")
    print(f"  HTML : {html_path}")
    print(f"  JSON : {data_path}")
    print(f"  汇总 : 共 {summary['total']} 例 | 通过 {summary['passed']} | "
          f"失败 {summary['failed']} | 错误 {summary['error']} | "
          f"跳过 {summary['skipped']} | 软性警告 {summary['soft_warnings']}")
    print("=" * 70)
