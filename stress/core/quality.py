"""质量四项检测（压测条款：字符重复 / 工具调用重复 / 串台 / 无意义输出）。

检测在响应到达时即时执行，原始文本只驻留内存；
确认的事故仅记录类型、会话、时间戳与截断证据。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class QualityIncident:
    kind: str                # char_repetition / toolcall_repetition / crosstalk / nonsense / claw_unexpected
    session_id: str
    ts: float
    detail: str


class CanaryRegistry:
    """每会话唯一 canary（UUID 主题），用于串台（cross-session leakage）检测。"""

    def __init__(self) -> None:
        self._by_session: dict[str, str] = {}

    def register(self, session_id: str) -> str:
        canary = f"CANARY-{uuid.uuid4().hex[:12]}"
        self._by_session[session_id] = canary
        return canary

    def foreign_canary_in(self, text: str, own_session: str) -> str | None:
        if "CANARY-" not in text:
            return None
        for sid, canary in self._by_session.items():
            if sid != own_session and canary in text:
                return canary
        return None


def check_char_repetition(text: str) -> str | None:
    """字符重复：任一 30 字符子串出现 ≥3 次（步进扫描近似）。"""
    if len(text) < 90:
        return None
    seen: dict[str, int] = {}
    step, width = 10, 30
    for i in range(0, len(text) - width, step):
        frag = text[i:i + width]
        seen[frag] = seen.get(frag, 0) + 1
        if seen[frag] >= 3:
            return f"30 字符片段重复 ≥3 次: {frag[:40]!r}"
    return None


def check_toolcall_repetition(tool_calls: list) -> str | None:
    """工具调用重复：同一响应内相同 (name, arguments) 出现 ≥3 次。"""
    counts: dict[tuple, int] = {}
    for tc in tool_calls:
        key = (tc.get("name", ""), tc.get("arguments", ""))
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 3:
            return f"相同 tool_call 重复 ≥3 次: {key[0]}"
    return None


def check_nonsense(finish_reason: str | None, text: str, n_tool_calls: int) -> str | None:
    """无意义输出（轻量规则）：finish=stop 但正文与 tool_calls 均为空。"""
    if finish_reason == "stop" and not text.strip() and n_tool_calls == 0:
        return "finish=stop 但输出为空"
    return None


def check_claw_finish(scenario: str, finish_reason: str | None) -> str | None:
    """claw 场景期望以 tool_calls 结束（比例高，作质量信号而非硬判）。"""
    if scenario.endswith("claw") and finish_reason not in (None, "tool_calls"):
        return f"{scenario} 场景 finish={finish_reason}（期望 tool_calls）"
    return None
