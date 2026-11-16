"""条目#3 max_tokens：默认值为 131072，允许用户修改。

- test_03_explicit_max_tokens_accepted：显式传 131072 必须被接受（轻量）；
- test_03_explicit_small_max_tokens_respected：显式传小值应生效（允许用户修改）；
- test_03_default_not_small：不传 max_tokens 时可生成超过 4096 tokens，
  证明默认值不是小值（中等耗时，约 2-5 分钟）；
- test_03_full_default_cap（heavy）：不传 max_tokens 持续生成直至 finish=length，
  验证实际上限达到 131072（极耗时，131072 tokens @30 OTPS 约 70+ 分钟，
  仅在 --include-heavy 时运行）。
"""

from __future__ import annotations

import pytest

DEFAULT_MAX_TOKENS = 131072


def test_03_explicit_max_tokens_accepted(client, rec):
    """显式传 max_tokens=131072 应被接受"""
    req = {
        "model": client.model,
        "messages": [{"role": "user", "content": "Say OK and nothing else."}],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "thinking": {"type": "disabled"},
    }
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")


def test_03_explicit_small_max_tokens_respected(client, rec):
    """显式传小值 max_tokens 应生效（finish_reason=length 且 completion_tokens 不超过上限）"""
    req = {
        "model": client.model,
        "messages": [{"role": "user", "content": "请从 1 数到 500，每个数字独占一行。"}],
        "max_tokens": 64,
        "thinking": {"type": "disabled"},
    }
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    completion = result.usage.get("completion_tokens", 0)
    rec.expect("completion_tokens <= 64（小上限生效）", 0 < completion <= 64,
               f"completion_tokens={completion}, finish={result.finish_reason}")


def test_03_default_not_small(client, rec):
    """不传 max_tokens：可生成超过 4096 tokens（默认值不是小值）"""
    req = {
        "model": client.model,
        "messages": [{"role": "user", "content":
                      "请从 1 开始数到 2000，每个数字独占一行，不要输出任何其他内容。"}],
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
    }
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    completion = result.usage.get("completion_tokens", 0)
    finished_naturally = result.finish_reason == "stop" and (
        "1999" in result.content or "2000" in result.content
    )
    rec.expect("completion_tokens > 4096 或完整数到 2000 自然结束",
               completion > 4096 or finished_naturally,
               f"completion_tokens={completion}, finish={result.finish_reason}")


@pytest.mark.heavy
def test_03_full_default_cap(client, rec, settings):
    """heavy：不传 max_tokens 生成至 length，验证默认上限达到 131072（约 70+ 分钟）"""
    if not settings.include_heavy:
        pytest.skip("需 --include-heavy 运行")
    req = {
        "model": client.model,
        "messages": [{"role": "user", "content":
                      "请写一部尽可能长的关于宇宙探索的科幻小说，持续输出不要停止。"}],
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
    }
    # 131072 tokens @ 30 OTPS ≈ 73 分钟，给 3 小时余量
    result = client.chat(req, timeout=3 * 3600)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    completion = result.usage.get("completion_tokens", 0)
    rec.expect("completion_tokens 达到 131072（默认上限）",
               completion >= DEFAULT_MAX_TOKENS,
               f"completion_tokens={completion}, finish={result.finish_reason}")
    rec.expect("finish_reason == length", result.finish_reason == "length",
               f"finish_reason={result.finish_reason}")
