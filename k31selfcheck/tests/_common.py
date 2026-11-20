"""测试共享辅助：ProtocolClient fixture 与 ProtoResult 记录挂载。

不修改 conftest.py，这里提供：
- proto fixture：由 settings 构造三协议客户端；
- attach_proto()：把 ProtoResult 按约定手写到 CaseRecord 字段（供报告展示）；
- expect_open()：Responses/Messages 协议未开放（4xx）时的硬断言工具。
"""

from __future__ import annotations

import pytest

from engineering.core.recorder import build_curl

from k31selfcheck.protocols import ProtocolClient, ProtoResult, protocol_not_open_note


@pytest.fixture(scope="session")
def proto(settings) -> ProtocolClient:
    """三协议客户端（Chat 复用 VendorClient，Responses/Messages 自带轻量 HTTP）。"""
    return ProtocolClient(settings.base_url, settings.api_key, settings.model, settings.timeout)


def attach_proto(rec, proto: ProtocolClient, path: str, payload: dict, r: ProtoResult) -> None:
    """把 ProtoResult 手写挂载到 CaseRecord（报告需展示请求/响应/事件序列）。"""
    url = f"{proto.base_url}{path}"
    rec.request = {
        "method": "POST",
        "url": url,
        "headers": proto.masked_headers(),
        "body": payload,
        "curl": build_curl("POST", url, proto.masked_headers(), payload),
    }
    rec.response_status = r.status_code
    rec.response = r.json_body if r.json_body is not None else r.raw_text
    rec.latency_s = round(r.latency_s, 3)
    rec.ttft_s = round(r.ttft_s, 3) if r.ttft_s is not None else None
    rec.usage = r.usage or {}
    rec.finish_reason = r.finish
    if r.events:
        rec.extra.setdefault("sse_events", r.events[:100])
    if r.response_headers:
        rec.extra.setdefault("response_headers", r.response_headers)
    if r.error:
        rec.error = r.error


def expect_protocol_open(rec, name: str, r: ProtoResult, path_desc: str) -> None:
    """协议未开放（HTTP 非 2xx）时硬断言失败并注明 protocol_not_open_note。

    按基线要求：未开放协议须在准出前确认不适用，不得以其他协议结果替代，
    不得静默跳过。
    """
    rec.expect(
        f"{name} HTTP 2xx",
        r.ok,
        f"status={r.status_code} err={r.error}\n{protocol_not_open_note(path_desc)}",
    )
