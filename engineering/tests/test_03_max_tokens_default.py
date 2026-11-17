"""条目#3 max_tokens：默认值为 131072，允许用户修改。

- test_03_explicit_max_tokens_accepted：显式传 131072 必须被接受（轻量）；
- test_03_explicit_small_max_tokens_respected：显式传小值应生效（允许用户修改）；
- test_03_default_not_small：不传 max_tokens 时可生成超过 4096 tokens，
  证明默认值不是小值（中等耗时，约 2-5 分钟）；
- test_03_full_default_cap（heavy）：不传 max_tokens，以确定性计数序列
  （从 1 数到 100000，约 25 万 tokens 工作量）逼出单次 completion 上限，
  验证默认上限 ≥ 131072；模型提前 stop 记"无法判定"不误判（最多重试 2 次，
  约 70+ 分钟/次，仅在 --include-heavy 时运行）。
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


def _counting_req(model: str, strict: bool = False) -> dict:
    """确定性序列输出：任务无客观终点，逼出单次 completion 上限。

    （旧版"写长篇小说" prompt 模型可提前收尾，实测 1335 即 stop，无法区分
    "上限不足"与"模型不想写"，故改用计数序列。）
    """
    text = ("任务：从 1 开始数到 100000，每个数字独占一行。必须数完，"
            "中途不要停止，不要输出任何其他内容。" if strict else
            "请从 1 开始数到 100000，每个数字独占一行，不要输出任何其他内容，中途不要停止。")
    return {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
    }


@pytest.mark.heavy
def test_03_full_default_cap(client, rec, settings):
    """heavy：不传 max_tokens，以计数序列逼出单次 completion 上限，验证默认上限 ≥ 131072。

    判定矩阵（约 70+ 分钟/次，最多 2 次）：
    - finish=length 且 completion ≥ 131072 → PASS（撞上限且达标；>131072 亦合规）
    - finish=length 且 completion < 131072 → FAIL（上限不足，确凿证据）
    - finish=stop（提前收尾）→ 无法判定，自动换措辞重试一次；仍 stop →
      记 skipped 无法判定（模型不愿写 ≠ 上限不足，不判供应商失败）
    """
    if not settings.include_heavy:
        pytest.skip("需 --include-heavy 运行")

    attempts = []
    for strict in (False, True):
        req = _counting_req(client.model, strict)
        # 131072 tokens @ 30 OTPS ≈ 73 分钟，单次给 3 小时余量
        result = client.chat(req, timeout=3 * 3600)
        rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
        completion = result.usage.get("completion_tokens", 0)
        attempts.append({"strict_prompt": strict, "completion_tokens": completion,
                         "finish_reason": result.finish_reason})
        rec.extra["attempts"] = attempts
        rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")

        if result.finish_reason == "length":
            # 撞到实际上限：有确凿结论
            rec.expect("completion_tokens ≥ 131072（默认上限达标）",
                       completion >= DEFAULT_MAX_TOKENS,
                       f"completion_tokens={completion}, finish=length")
            return
        if completion >= DEFAULT_MAX_TOKENS:
            # 未撞上限但产出已超 131072：上限合规
            rec.expect("completion_tokens ≥ 131072（未撞上限，默认上限合规）", True,
                       f"completion_tokens={completion}, finish={result.finish_reason}")
            return
        # 模型提前收尾：本次无法判定，换措辞重试
        rec.check("模型提前 stop，无法判定上限（自动换措辞重试）", False,
                  f"completion_tokens={completion}, finish={result.finish_reason}", soft=True)

    # 两次均提前 stop：无法判定（不构成上限不足的证据）
    pytest.skip(
        "默认上限无法判定：两次计数尝试模型均提前 stop "
        f"(completion_tokens={[a['completion_tokens'] for a in attempts]})。"
        "模型提前收尾 ≠ 上限不足；建议人工确认供应商默认上限或请其提供证明。"
    )
