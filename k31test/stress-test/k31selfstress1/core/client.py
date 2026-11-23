"""异步客户端：流式请求采集 TTFT / 逐 chunk 到达时间 / usage；非流式请求。

TTFT = 请求发出 → 首个内容/思考 chunk 到达的时延；
TPOT（单请求）= (末内容 chunk 时刻 − 首内容 chunk 时刻) / (completion_tokens − 1)。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class StreamResult:
    status: int = 0
    error: str | None = None
    t_start: float = 0.0
    total_ms: float = 0.0
    ttft_ms: float | None = None
    chunk_times: list[float] = field(default_factory=list)  # perf_counter 相对 t_start 的秒
    content_chars: int = 0
    reasoning_chars: int = 0
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300

    @property
    def prompt_tokens(self) -> int:
        return int(self.usage.get("prompt_tokens") or 0)

    @property
    def completion_tokens(self) -> int:
        return int(self.usage.get("completion_tokens") or 0)

    @property
    def cached_tokens(self) -> int:
        details = self.usage.get("prompt_tokens_details") or {}
        val = details.get("cached_tokens")
        if val is None:
            val = self.usage.get("cached_tokens")
        return int(val or 0)

    @property
    def tpot_ms(self) -> float | None:
        """(末 chunk − 首 chunk)/(completion_tokens−1)；样本不足返回 None。"""
        if len(self.chunk_times) < 2 or self.completion_tokens < 2:
            return None
        span_ms = (self.chunk_times[-1] - self.chunk_times[0]) * 1000
        return span_ms / (self.completion_tokens - 1)


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


class PerfClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.deploy_id: str = ""

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def stream_chat(self, payload: dict) -> StreamResult:
        """流式请求：采集 TTFT、逐内容 chunk 到达时刻（相对 t_start 秒）、usage。"""
        r = StreamResult()
        t0 = time.perf_counter()
        r.t_start = t0
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.chat_url, json=payload,
                                         headers=_auth_headers(self.api_key)) as resp:
                    r.status = resp.status_code
                    self.deploy_id = self.deploy_id or resp.headers.get(
                        "x-msh-providerdeployid", "")
                    if r.status != 200:
                        r.error = f"HTTP {r.status}: {(await resp.aread())[:300]!r}"
                        r.total_ms = (time.perf_counter() - t0) * 1000
                        return r
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        now = time.perf_counter() - t0
                        has_delta = False
                        for ch in obj.get("choices") or []:
                            delta = ch.get("delta") or {}
                            if delta.get("content"):
                                r.content_chars += len(delta["content"])
                                has_delta = True
                            if delta.get("reasoning_content"):
                                r.reasoning_chars += len(delta["reasoning_content"])
                                has_delta = True
                            if delta.get("tool_calls"):
                                has_delta = True
                            if ch.get("finish_reason"):
                                r.finish_reason = ch["finish_reason"]
                        if obj.get("usage"):
                            r.usage = obj["usage"]
                        if has_delta:
                            r.chunk_times.append(now)
        except httpx.HTTPError as exc:
            r.error = f"{type(exc).__name__}: {exc}"
        r.total_ms = (time.perf_counter() - t0) * 1000
        if r.chunk_times:
            r.ttft_ms = r.chunk_times[0] * 1000
        return r

    async def chat(self, payload: dict) -> StreamResult:
        """非流式请求（缓存场景 warm/probe 用）。"""
        r = StreamResult()
        t0 = time.perf_counter()
        r.t_start = t0
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.chat_url, json=payload,
                                         headers=_auth_headers(self.api_key))
                r.status = resp.status_code
                self.deploy_id = self.deploy_id or resp.headers.get(
                    "x-msh-providerdeployid", "")
                if r.status == 200:
                    body = resp.json()
                    r.usage = body.get("usage") or {}
                    choices = body.get("choices") or []
                    if choices:
                        r.finish_reason = choices[0].get("finish_reason")
                        msg = choices[0].get("message") or {}
                        r.content_chars = len(msg.get("content") or "")
                else:
                    r.error = f"HTTP {r.status}: {resp.text[:300]!r}"
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            r.error = f"{type(exc).__name__}: {exc}"
        r.total_ms = (time.perf_counter() - t0) * 1000
        return r
