"""三协议客户端：Chat(/v1/chat/completions)、Responses(/v1/responses)、
Messages(/anthropic/v1/messages) 的非流式 + 流式调用与解析。

设计原则：
- Chat 复用 engineering.core.client.VendorClient（含 SSE 重组/TTFT/usage）；
- Responses / Messages 自带轻量 HTTP 与 SSE 事件采集（事件名序列 + 增量重组 +
  终态识别），不假设供应商已实现（404/400 时返回结构化结果供上层判定"协议未开放"）。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from engineering.core.client import ChatResult, VendorClient

_MAX_RAW = 1_000_000


@dataclass
class ProtoResult:
    """单协议调用结果（非流式或流式统一视图）。"""
    ok: bool = False
    status_code: int | None = None
    error: str | None = None
    latency_s: float = 0.0
    ttft_s: float | None = None
    json_body: dict | None = None      # 非流式响应体；流式时为重组后结构
    raw_text: str = ""
    # 流式专有
    events: list[str] = field(default_factory=list)     # SSE 事件名序列
    text: str = ""
    reasoning_text: str = ""
    finish: str | None = None          # 终态（finish_reason/stop_reason/status）
    usage: dict = field(default_factory=dict)
    n_chunks: int = 0
    response_headers: dict = field(default_factory=dict)

    @property
    def not_found(self) -> bool:
        return self.status_code in (400, 404, 405, 422)


class ProtocolClient:
    """三协议调用客户端。model 默认取 settings.model。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.chat = VendorClient(base_url, api_key, model, timeout)

    # ------------------------------------------------------------ 基础工具
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def masked_headers(self) -> dict:
        tail = self.api_key[-4:] if len(self.api_key) >= 4 else "****"
        return {"Authorization": f"Bearer ***{tail}", "Content-Type": "application/json"}

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(timeout=httpx.Timeout(connect=30.0, read=timeout, write=60.0, pool=60.0))

    def _full_url(self, path: str) -> str:
        """协议路径为根相对路径（/v1/responses、/anthropic/v1/messages）：
        base_url 若含 /v1 后缀须先归一到 origin 再拼接，避免出现 /v1/v1/... 错误路径。"""
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base}{path}"

    # ------------------------------------------------------------ Chat（复用）
    def call_chat(self, payload: dict, timeout: float | None = None) -> ChatResult:
        return self.chat.chat(payload, timeout=timeout)

    # ------------------------------------------------------------ 通用请求/SSE
    def _post(self, path: str, payload: dict, timeout: float | None = None) -> ProtoResult:
        url = self._full_url(path)
        t = float(timeout or self.timeout)
        started = time.monotonic()
        r = ProtoResult()
        try:
            with self._client(t) as c:
                resp = c.post(url, json=payload, headers=self._headers())
            r.latency_s = r.ttft_s = time.monotonic() - started
            r.status_code = resp.status_code
            r.response_headers = dict(resp.headers)
            r.raw_text = resp.text[:_MAX_RAW]
            if 200 <= resp.status_code < 300:
                r.ok = True
                try:
                    r.json_body = resp.json()
                    r.usage = (r.json_body or {}).get("usage") or {}
                except json.JSONDecodeError:
                    r.ok = False
                    r.error = "响应非 JSON"
            else:
                r.error = f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            r.error = f"{type(exc).__name__}: {exc}"
            r.latency_s = time.monotonic() - started
        return r

    def _post_stream(self, path: str, payload: dict, timeout: float | None = None) -> ProtoResult:
        url = self._full_url(path)
        t = float(timeout or self.timeout)
        started = time.monotonic()
        r = ProtoResult()
        lines: list[str] = []
        n_chars = 0
        first_chunk_at: float | None = None
        last_chunk_at: float | None = None
        try:
            with self._client(t) as c:
                with c.stream("POST", url, json=payload, headers=self._headers()) as resp:
                    r.status_code = resp.status_code
                    r.response_headers = dict(resp.headers)
                    if not (200 <= resp.status_code < 300):
                        body = resp.read().decode("utf-8", errors="replace")
                        r.raw_text = body[:_MAX_RAW]
                        r.error = f"HTTP {resp.status_code}"
                        r.latency_s = time.monotonic() - started
                        return r
                    for line in resp.iter_lines():
                        if first_chunk_at is None and (line.startswith("data:") or line.startswith("event:")):
                            first_chunk_at = time.monotonic()
                        last_chunk_at = time.monotonic()
                        n_chars += len(line) + 1
                        if n_chars <= _MAX_RAW:
                            lines.append(line)
            r.ok = True
            r.latency_s = time.monotonic() - started
            r.ttft_s = (first_chunk_at - started) if first_chunk_at else None
            r.raw_text = "\n".join(lines)
            self._parse_sse(lines, r)
        except httpx.HTTPError as exc:
            r.error = f"{type(exc).__name__}: {exc}"
            r.latency_s = time.monotonic() - started
        return r

    def _parse_sse(self, lines: list[str], r: ProtoResult) -> None:
        cur_event = ""
        for line in lines:
            if line.startswith("event:"):
                cur_event = line[6:].strip()
                r.events.append(cur_event)
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                continue
            r.n_chunks += 1
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if cur_event:
                if not r.events or r.events[-1] != cur_event:
                    r.events.append(cur_event)
            if isinstance(chunk, dict):
                if chunk.get("usage"):
                    r.usage = chunk["usage"]
                # responses.completed / messages usage 在终块
                if chunk.get("response") and isinstance(chunk["response"], dict):
                    u = chunk["response"].get("usage")
                    if u:
                        r.usage = u
                if chunk.get("message") and isinstance(chunk["message"], dict):
                    u = chunk["message"].get("usage")
                    if u:
                        r.usage = {**r.usage, **u}

    # ------------------------------------------------------------ Responses
    RESPONSES_PATH = "/v1/responses"

    def call_responses(self, payload: dict, stream: bool = False,
                       timeout: float | None = None) -> ProtoResult:
        body = dict(payload)
        body.setdefault("model", self.model)
        if stream:
            body["stream"] = True
            return self._post_stream(self.RESPONSES_PATH, body, timeout)
        return self._post(self.RESPONSES_PATH, body, timeout)

    # ------------------------------------------------------------ Messages
    MESSAGES_PATH = "/anthropic/v1/messages"

    def call_messages(self, payload: dict, stream: bool = False,
                      timeout: float | None = None) -> ProtoResult:
        body = dict(payload)
        body.setdefault("model", self.model)
        if stream:
            body["stream"] = True
            return self._post_stream(self.MESSAGES_PATH, body, timeout)
        return self._post(self.MESSAGES_PATH, body, timeout)


# ------------------------------------------------------------------ 协议提取辅助
def responses_output_types(result: ProtoResult) -> list[str]:
    out = (result.json_body or {}).get("output") or []
    return [i.get("type") for i in out if isinstance(i, dict)]


def responses_text(result: ProtoResult) -> str:
    parts = []
    for item in (result.json_body or {}).get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for c in item.get("content") or []:
                if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text", ""))
    return "".join(parts)


def responses_reasoning_types(result: ProtoResult) -> list[str]:
    return [t for t in responses_output_types(result) if t == "reasoning"]


def messages_content_types(result: ProtoResult) -> list[str]:
    out = (result.json_body or {}).get("content") or []
    return [i.get("type") for i in out if isinstance(i, dict)]


def messages_text(result: ProtoResult) -> str:
    parts = []
    for c in (result.json_body or {}).get("content") or []:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(c.get("text", ""))
    return "".join(parts)


def protocol_not_open_note(path_desc: str) -> str:
    return (f"{path_desc} 未开放（HTTP 非 2xx）。按基线要求：未开放协议须在准出前确认不适用，"
            "不得以其他协议结果替代。")
