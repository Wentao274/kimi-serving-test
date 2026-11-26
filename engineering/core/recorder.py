"""用例记录器：结构化收集每个测试用例的请求/响应/断言，供 HTML 报告渲染。"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def build_curl(method: str, url: str, masked_headers: dict, body: dict | None) -> str:
    """生成可直接复制执行的 curl 复现命令（API key 已脱敏）。"""
    import json as _json
    parts = [f"curl -X {method} '{url}'"]
    for k, v in (masked_headers or {}).items():
        parts.append(f"  -H '{k}: {v}'")
    if body is not None:
        parts.append(f"  -d '{_json.dumps(body, ensure_ascii=False)}'")
    return " \\\n".join(parts)


@dataclass
class Assertion:
    name: str
    passed: bool
    detail: str = ""
    soft: bool = False      # soft 断言失败不阻断测试（记录为警告）


@dataclass
class CaseRecord:
    suite: str                       # 测试模块名，如 test_e01_connectivity
    case_id: str                     # pytest nodeid
    title: str
    description: str = ""
    started_at: str = ""
    request: dict | None = None      # {"method","url","headers(masked)","body"}
    response_status: int | None = None
    response: Any = None             # 响应 JSON（流式为重组对象）或原始文本
    latency_s: float | None = None
    ttft_s: float | None = None
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None
    assertions: list[Assertion] = field(default_factory=list)
    outcome: str = "passed"          # passed / failed / error / skipped
    error: str = ""
    extra: dict = field(default_factory=dict)   # 备注信息（如 reasoning 长度、探针响应等）

    def check(self, name: str, passed: bool, detail: str = "", soft: bool = False) -> None:
        """记录一条断言（不抛出异常，是否中断由测试代码的 assert 决定）。"""
        self.assertions.append(Assertion(name=name, passed=bool(passed), detail=detail, soft=soft))

    def expect(self, name: str, passed: bool, detail: str = "") -> None:
        """记录断言并以 pytest 语义中断（等价于 check + assert）。"""
        self.check(name, passed, detail)
        assert passed, f"{name}: {detail}"

    def attach_result(self, request_body: dict, result, url: str, masked_headers: dict) -> None:
        """把 VendorClient.chat 的结果附加到记录上。"""
        self.request = {
            "method": "POST",
            "url": url,
            "headers": masked_headers,
            "body": request_body,
            "curl": build_curl("POST", url, masked_headers, request_body),
        }
        self.response_status = result.status_code
        # 流式请求保存原始 SSE 文本作为响应证据（而非重组消息）；非流式仍存 response_json
        if getattr(result, "stream", False):
            self.response = result.raw_text or result.response_json
        else:
            self.response = result.response_json if result.response_json is not None else result.raw_text
        self.latency_s = round(result.latency_s, 3)
        self.ttft_s = round(result.ttft_s, 3) if result.ttft_s is not None else None
        self.usage = result.usage or {}
        self.finish_reason = result.finish_reason
        if result.response_headers:
            self.extra.setdefault("response_headers", result.response_headers)
        if result.error:
            self.error = result.error

    def attach_raw(self, method: str, url: str, masked_headers: dict,
                   status: int | None, body_text: str, latency_s: float, error: str | None = None) -> None:
        """附加非 chat 类请求（如 GET /models）。"""
        self.request = {"method": method, "url": url, "headers": masked_headers, "body": None,
                        "curl": build_curl(method, url, masked_headers, None)}
        self.response_status = status
        self.response = body_text
        self.latency_s = round(latency_s, 3)
        if error:
            self.error = error


class Collector:
    """会话级收集器（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[CaseRecord] = []
        self.started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        self.finished_at: str = ""

    def add(self, record: CaseRecord) -> None:
        with self._lock:
            self.records.append(record)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def summary(self) -> dict[str, int]:
        counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "soft_warnings": 0}
        for r in self.records:
            counts[r.outcome] = counts.get(r.outcome, 0) + 1
            counts["soft_warnings"] += sum(1 for a in r.assertions if a.soft and not a.passed)
        counts["total"] = len(self.records)
        return counts

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary(),
            "records": [asdict(r) for r in self.records],
        }
