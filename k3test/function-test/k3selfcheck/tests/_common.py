"""k3selfcheck 共享辅助：通用规则硬校验、常用请求构造 + 三协议 fixture 与记录挂载。

通用规则（测试通过标准通用规则）：接口正常调用返回 200、无报错、无超时、
无空响应；输出内容无乱码（无替换符 �）。
"""

from __future__ import annotations

import json

import pytest

from engineering.core.client import ChatResult, VendorClient
from engineering.core.recorder import build_curl

from k3selfcheck.protocols import ProtocolClient, ProtoResult, protocol_not_open_note

REPLACEMENT_CHAR = "�"


def has_mojibake(text: str | None) -> bool:
    """content 出现 Unicode 替换符 � 视为乱码。"""
    return bool(text) and REPLACEMENT_CHAR in text


def send(client: VendorClient, rec, payload: dict, timeout: float | None = None) -> ChatResult:
    """发送 chat 请求并附加到用例记录（报告展示请求/响应/curl）。"""
    r = client.chat(payload, timeout=timeout)
    rec.attach_result(payload, r, client.chat_completions_url, client.masked_headers())
    return r


def expect_common_ok(rec, r: ChatResult, *, require_content: bool = True) -> None:
    """通用规则硬校验：HTTP 200、无报错/无超时、无空响应、content 无乱码。"""
    rec.expect("HTTP 200", r.ok and r.status_code == 200,
               f"status={r.status_code} err={r.error}")
    rec.expect("无报错/无超时（网络与解析正常）", r.error is None, f"error={r.error!r}")
    if require_content:
        rec.expect("无空响应（content 非空）", bool(r.content),
                   f"content_len={len(r.content or '')} tool_calls={len(r.tool_calls)}")
        rec.expect("content 无乱码（无替换符 �）", not has_mojibake(r.content),
                   f"content[:120]={(r.content or '')[:120]!r}")


def expect_4xx(rec, name: str, r: ChatResult) -> None:
    """负向用例硬校验：返回 4xx 且无网络/超时异常。"""
    rec.expect(f"{name} 返回 4xx",
               r.status_code is not None and 400 <= r.status_code < 500,
               f"status={r.status_code} err={r.error}")
    rec.expect(f"{name} 无网络/超时错误", r.error is None, f"error={r.error!r}")


def error_body(r: ChatResult) -> dict | None:
    """解析错误响应体（非 2xx 时 response_json 为空，从 raw_text 解析）。"""
    if isinstance(r.response_json, dict):
        return r.response_json
    try:
        obj = json.loads(r.raw_text) if r.raw_text else None
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def error_message(body: dict | None) -> str:
    """从 OpenAI 风格错误体提取 message 文本。"""
    if not isinstance(body, dict):
        return ""
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or "")
    if isinstance(err, str):
        return err
    return str(body.get("message") or "")


def make_long_text(target_chars: int, seed: str | None = None) -> str:
    """构造确定性的长文本（带编号避免完全重复），长度 ≥ target_chars。"""
    seed = seed or "人工智能与大规模语言模型正在深刻改变软件开发、科学研究与工业生产的方式。"
    parts: list[str] = []
    total = 0
    i = 0
    while total < target_chars:
        seg = f"【第{i}段】{seed}"
        parts.append(seg)
        total += len(seg)
        i += 1
    return "".join(parts)


def sse_chunks(raw: str) -> list[dict]:
    """解析 SSE data 行为 JSON chunk 列表（忽略 [DONE] 与解析失败的行）。"""
    chunks: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            chunks.append(obj)
    return chunks


# ---------------------------------------------------------------- 三协议支持


@pytest.fixture(scope="session")
def proto(settings) -> ProtocolClient:
    """三协议客户端（Chat 复用 VendorClient，Responses/Messages 自带轻量 HTTP）。"""
    return ProtocolClient(settings.base_url, settings.api_key, settings.model, settings.timeout)


def attach_proto(rec, proto: ProtocolClient, path: str, payload: dict, r: ProtoResult) -> None:
    """把 ProtoResult 写回对应的 CaseRecord（报告展示请求/响应/事件序列）。"""
    url = proto._full_url(path)  # 与实际发送的请求 URL 保持一致（避免展示成双 /v1）
    # 与实际发送的请求体一致：call_responses/call_messages 会注入 model
    body = dict(payload)
    body.setdefault("model", proto.model)
    rec.request = {
        "method": "POST",
        "url": url,
        "headers": proto.masked_headers(),
        "body": body,
        "curl": build_curl("POST", url, proto.masked_headers(), body),
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
    """协议未开放（HTTP 非 2xx）时硬断言失败并注明 protocol_not_open_note。"""
    rec.expect(
        f"{name} HTTP 2xx",
        r.ok,
        f"status={r.status_code} err={r.error}\n{protocol_not_open_note(path_desc)}",
    )
