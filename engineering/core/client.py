"""OpenAI 兼容 HTTP 客户端：支持流式/非流式，记录 TTFT/时延/usage，SSE 重组。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# 报告中原始响应体的最大保留字符数（防止超大 SSE 占用内存）
_MAX_RAW_CHARS = 1_000_000


@dataclass
class ChatResult:
    """一次 chat/completions 调用的结构化结果。"""

    ok: bool = False                     # HTTP 2xx 且解析完成
    status_code: int | None = None
    error: str | None = None             # 网络/解析异常描述（HTTP 非 2xx 不算 error）
    stream: bool = False
    content: str = ""
    reasoning_content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
    response_json: dict | None = None    # 非流式：完整响应 JSON；流式：重组后的响应对象
    raw_text: str = ""                   # 原始响应体（可能被截断）
    latency_s: float = 0.0
    ttft_s: float | None = None          # 流式：首个 data chunk 时间；非流式：整体时间
    n_chunks: int = 0
    response_headers: dict = field(default_factory=dict)   # 响应头（用于 trace 检查）


def merge_tool_call_fragments(fragments: list[dict]) -> list[dict]:
    """把流式 tool_calls delta 按 index 合并为完整 tool_calls 列表。"""
    merged: dict[int, dict] = {}
    for frag in fragments:
        idx = frag.get("index", 0)
        slot = merged.setdefault(
            idx,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if frag.get("id"):
            slot["id"] = frag["id"]
        if frag.get("type"):
            slot["type"] = frag["type"]
        fn = frag.get("function") or {}
        if fn.get("name"):
            slot["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]
    return [merged[i] for i in sorted(merged)]


def reassemble_sse(raw_text: str) -> ChatResult:
    """将 SSE 原始文本重组为完整响应。独立纯函数，便于离线单测。"""
    result = ChatResult(stream=True)
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_frags: list[dict] = []
    last_chunk: dict | None = None

    for line in raw_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        result.n_chunks += 1
        last_chunk = chunk
        if chunk.get("error"):
            result.error = json.dumps(chunk["error"], ensure_ascii=False)
        if chunk.get("usage"):
            result.usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])
            if delta.get("tool_calls"):
                tool_frags.extend(delta["tool_calls"])
            if choice.get("finish_reason"):
                result.finish_reason = choice["finish_reason"]

    result.content = "".join(content_parts)
    result.reasoning_content = "".join(reasoning_parts)
    result.tool_calls = merge_tool_call_fragments(tool_frags)

    base = {k: v for k, v in (last_chunk or {}).items() if k not in ("choices",)}
    base["choices"] = [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": result.content,
                "reasoning_content": result.reasoning_content,
                "tool_calls": result.tool_calls,
            },
            "finish_reason": result.finish_reason,
        }
    ]
    result.response_json = base
    return result


class VendorClient:
    """指向供应商 endpoint 的 chat/completions 客户端。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------ utils
    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/models"

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def masked_headers(self) -> dict[str, str]:
        tail = self.api_key[-4:] if len(self.api_key) >= 4 else "****"
        return {"Authorization": f"Bearer ***{tail}", "Content-Type": "application/json"}

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=timeout, write=60.0, pool=60.0),
        )

    # ----------------------------------------------------------------- models
    def get_models(self, timeout: float = 60.0) -> tuple[int | None, str, float, str | None]:
        """GET /models → (status, body_text, latency_s, error)。"""
        url = f"{self.base_url}/models"
        started = time.monotonic()
        try:
            with self._client(timeout) as c:
                resp = c.get(url, headers=self.headers())
            return resp.status_code, resp.text[:_MAX_RAW_CHARS], time.monotonic() - started, None
        except httpx.HTTPError as exc:
            return None, "", time.monotonic() - started, f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------- chat
    def chat(self, request: dict[str, Any], timeout: float | None = None,
             extra_headers: dict[str, str] | None = None) -> ChatResult:
        """发送 chat/completions 请求（自动按 request.stream 分流）。"""
        req = dict(request)
        stream = bool(req.get("stream"))
        url = f"{self.base_url}/chat/completions"
        timeout = float(timeout or self.timeout)
        headers = {**self.headers(), **(extra_headers or {})}
        started = time.monotonic()

        try:
            with self._client(timeout) as c:
                if stream:
                    return self._chat_stream(c, url, req, headers, started)
                return self._chat_once(c, url, req, headers, started)
        except httpx.HTTPError as exc:
            return ChatResult(
                ok=False,
                stream=stream,
                error=f"{type(exc).__name__}: {exc}",
                latency_s=time.monotonic() - started,
            )

    def _chat_once(self, c: httpx.Client, url: str, req: dict,
                   headers: dict, started: float) -> ChatResult:
        resp = c.post(url, json=req, headers=headers)
        latency = time.monotonic() - started
        result = ChatResult(
            status_code=resp.status_code,
            stream=False,
            raw_text=resp.text[:_MAX_RAW_CHARS],
            latency_s=latency,
            ttft_s=latency,
            response_headers=dict(resp.headers),
        )
        result.ok = 200 <= resp.status_code < 300
        if result.ok:
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                result.ok = False
                result.error = f"响应非 JSON: {exc}"
                return result
            result.response_json = data
            result.usage = data.get("usage") or {}
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                result.content = msg.get("content") or ""
                result.reasoning_content = msg.get("reasoning_content") or ""
                result.tool_calls = msg.get("tool_calls") or []
                result.finish_reason = choices[0].get("finish_reason")
        return result

    def _chat_stream(self, c: httpx.Client, url: str, req: dict,
                     headers: dict, started: float) -> ChatResult:
        lines: list[str] = []
        n_chars = 0
        ttft: float | None = None
        status: int | None = None
        with c.stream("POST", url, json=req, headers=headers) as resp:
            status = resp.status_code
            resp_headers = dict(resp.headers)
            if not (200 <= resp.status_code < 300):
                body = resp.read().decode("utf-8", errors="replace")
                return ChatResult(
                    ok=False,
                    status_code=status,
                    stream=True,
                    raw_text=body[:_MAX_RAW_CHARS],
                    latency_s=time.monotonic() - started,
                    response_headers=resp_headers,
                )
            for line in resp.iter_lines():
                if ttft is None and line.startswith("data:") and line.strip() != "data:":
                    ttft = time.monotonic() - started
                n_chars += len(line) + 1
                if n_chars <= _MAX_RAW_CHARS:
                    lines.append(line)
        raw = "\n".join(lines)
        result = reassemble_sse(raw)
        result.ok = True
        result.status_code = status
        result.raw_text = raw
        result.latency_s = time.monotonic() - started
        result.ttft_s = ttft
        result.response_headers = resp_headers
        return result
