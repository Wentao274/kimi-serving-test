"""异步流式客户端：逐请求捕获 TTFT / 生成时长 / OTPS / usage / cached_tokens。

压测全部使用 stream=true（生产主路径 + TTFT 测量需要）。
文本与 tool_calls 仅驻留内存供质量检测，不落盘（闭源数据合规）。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class RequestOutcome:
    started_ts: float = 0.0            # epoch 秒（请求发出时刻）
    status: int | None = None
    error: str | None = None           # 网络/解析异常
    ttft_s: float | None = None        # 首 data chunk 时间
    gen_s: float | None = None         # 首 chunk → 末 chunk 时长
    total_s: float = 0.0
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    completion_tokens: int | None = None
    otps: float | None = None          # completion_tokens / gen_s
    text: str = ""                     # 内存态，供质量检测（默认不落盘）
    tool_calls: list = field(default_factory=list)

    @property
    def uncached_tokens(self) -> int | None:
        if self.prompt_tokens is None:
            return None
        return self.prompt_tokens - (self.cached_tokens or 0)

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and self.error is None


def _extract_cached(usage: dict) -> int | None:
    if not isinstance(usage, dict):
        return None
    if isinstance(usage.get("cached_tokens"), int):
        return usage["cached_tokens"]
    details = usage.get("prompt_tokens_details") or {}
    val = details.get("cached_tokens")
    return val if isinstance(val, int) else None


def _merge_tool_fragment(acc: dict, frag: dict) -> None:
    idx = frag.get("index", 0)
    slot = acc.setdefault(idx, {"name": "", "arguments": ""})
    fn = frag.get("function") or {}
    if fn.get("name"):
        slot["name"] += fn["name"]
    if fn.get("arguments"):
        slot["arguments"] += fn["arguments"]


class AsyncVendorClient:
    """httpx 异步客户端（高并发共享连接池）。"""

    def __init__(self, base_url: str, api_key: str, timeout: float, max_connections: int = 512):
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=timeout, write=60.0, pool=60.0),
            limits=httpx.Limits(max_connections=max_connections,
                                max_keepalive_connections=max_connections),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream_chat(self, payload: dict) -> RequestOutcome:
        """发送流式 chat/completions，逐 chunk 计时。"""
        req = dict(payload)
        req["stream"] = True
        req.setdefault("stream_options", {"include_usage": True})
        url = f"{self.base_url}/chat/completions"
        outcome = RequestOutcome(started_ts=time.time())
        started = time.monotonic()
        first_chunk_at: float | None = None
        last_chunk_at: float | None = None
        text_parts: list[str] = []
        tool_acc: dict[int, dict] = {}
        usage: dict = {}

        try:
            async with self._client.stream("POST", url, json=req, headers=self._headers) as resp:
                outcome.status = resp.status_code
                if not (200 <= resp.status_code < 300):
                    await resp.aread()
                    outcome.total_s = time.monotonic() - started
                    outcome.ttft_s = outcome.total_s   # 429/5xx 的"立即返回"时延
                    return outcome
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    now = time.monotonic()
                    if first_chunk_at is None:
                        first_chunk_at = now
                        outcome.ttft_s = now - started
                    last_chunk_at = now
                    if data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text_parts.append(delta["content"])
                        for frag in delta.get("tool_calls") or []:
                            _merge_tool_fragment(tool_acc, frag)
                        if choice.get("finish_reason"):
                            outcome.finish_reason = choice["finish_reason"]
        except httpx.HTTPError as exc:
            outcome.error = f"{type(exc).__name__}: {exc}"
            outcome.total_s = time.monotonic() - started
            return outcome

        outcome.total_s = time.monotonic() - started
        if first_chunk_at is not None and last_chunk_at is not None:
            outcome.gen_s = max(last_chunk_at - first_chunk_at, 0.0)
        outcome.text = "".join(text_parts)
        outcome.tool_calls = [tool_acc[i] for i in sorted(tool_acc)]
        outcome.prompt_tokens = usage.get("prompt_tokens")
        outcome.cached_tokens = _extract_cached(usage)
        outcome.completion_tokens = usage.get("completion_tokens")
        if outcome.completion_tokens is not None and outcome.gen_s and outcome.gen_s > 0:
            outcome.otps = outcome.completion_tokens / outcome.gen_s
        return outcome
