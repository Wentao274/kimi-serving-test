"""输入构造与分档校准（无 tokenizer 的黑盒方案）。

- filler_text：确定性中文填充文本（编号段落，防完全重复）；
- calibrate_ratio：发送一次校准请求，按 usage.prompt_tokens 得 字符/token 比；
- 逐请求唯一 nonce 前缀：保证冷请求（cached_tokens=0）。
"""

from __future__ import annotations

import uuid

_SEED = "人工智能与大规模语言模型正在深刻改变软件开发、科学研究与工业生产的方式，"


def filler_text(target_chars: int) -> str:
    """构造确定性的长文本（带编号避免完全重复），长度 ≥ target_chars。"""
    parts: list[str] = []
    total = 0
    i = 0
    while total < target_chars:
        seg = f"【第{i}段】{_SEED}"
        parts.append(seg)
        total += len(seg)
        i += 1
    return "".join(parts)


def nonce_prefix() -> str:
    """逐请求唯一前缀（保证不命中前缀缓存）。"""
    return f"n0nc3-{uuid.uuid4().hex[:16]}"


def calibrate_ratio(prompt_tokens: int, prompt_chars: int) -> float:
    """字符/token 比（校准请求实测得出）。"""
    if prompt_tokens <= 0:
        return 2.0  # 兜底估算（中文混合文本约 2 字符/token）
    return prompt_chars / prompt_tokens


def tokens_to_chars(tokens: int, ratio: float) -> int:
    return max(256, int(tokens * ratio))
