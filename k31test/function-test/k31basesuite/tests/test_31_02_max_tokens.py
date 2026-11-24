"""3.1 max_tokens：和官方模型对齐（kimi-k3.1-pro max_tokens 默认值 131072），允许用户修改。

kimi-k3.1-pro 官方规格：默认 131072、最大可设置 1048576；显式传 ≤1048576 被接受，
显式传 >1048576 应被拒绝（400）。
不传时默认上限的严格验证为 heavy 用例：以确定性计数序列（从 1 数到 100000，
约 25 万 tokens 工作量）逼出单次 completion 上限，验证默认上限 ≥ 131072
（需 --include-heavy，约 70+ 分钟/次，最多 2 次措辞重试；模型提前 stop 记
"无法判定"不误判）。
"""

from __future__ import annotations

import pytest

from k31basesuite.tests._common import expect_4xx, expect_common_ok, send

_OFFICIAL_DEFAULT_MAX_TOKENS = 131072


def _counting_req(model: str, strict: bool = False) -> dict:
    """确定性序列输出：任务无客观终点，逼出单次 completion 上限。

    （"写长文"类 prompt 模型可提前收尾，无法区分"上限不足"与"模型不想写"，
    故改用计数序列；disabled + 官方默认 temperature=0.6 降低随机性。）
    """
    text = ("任务：从 1 开始数到 100000，每个数字独占一行。必须数完，"
            "中途不要停止，不要输出任何其他内容。" if strict else
            "请从 1 开始数到 100000，每个数字独占一行，不要输出任何其他内容，中途不要停止。")
    return {"model": model, "messages": [{"role": "user", "content": text}],
            "thinking": {"type": "disabled"}, "temperature": 0.6}


@pytest.mark.heavy
def test_31_02_不传时默认上限131072验证(client, rec, settings):
    """max_tokens：不传时以计数序列逼出单次上限，验证默认上限 ≥ 131072（heavy，需 --include-heavy）

    判定矩阵：
    - finish=length 且 completion ≥ 131072 → PASS（撞上限且达标）
    - completion ≥ 131072 且未撞上限 → PASS（产出已超默认上限）
    - finish=length 且 completion < 131072 → FAIL（上限不足，确凿证据）
    - finish=stop（提前收尾）→ 无法判定，换措辞重试一次；仍 stop → skipped（不误判）
    """
    if not settings.include_heavy:
        pytest.skip("需 --include-heavy 运行（131072 tokens @ 30 OTPS ≈ 73 分钟/次，最多 2 次）")

    attempts = []
    for strict in (False, True):
        req = _counting_req(client.model, strict)
        # 131072 tokens @ 30 OTPS ≈ 73 分钟，单次给 3 小时余量
        r = send(client, rec, req, timeout=3 * 3600)
        completion = int((r.usage or {}).get("completion_tokens") or 0)
        attempts.append({"strict_prompt": strict, "completion_tokens": completion,
                         "finish_reason": r.finish_reason})
        rec.extra["attempts"] = attempts
        rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")

        if r.finish_reason == "length":
            rec.expect("completion_tokens ≥ 131072（默认上限达标）",
                       completion >= _OFFICIAL_DEFAULT_MAX_TOKENS,
                       f"completion_tokens={completion}, finish=length")
            return
        if completion >= _OFFICIAL_DEFAULT_MAX_TOKENS:
            rec.expect("completion_tokens ≥ 131072（未撞上限，默认上限合规）", True,
                       f"completion_tokens={completion}, finish={r.finish_reason}")
            return
        # 模型提前收尾：本次无法判定，换措辞重试
        rec.check("模型提前 stop，无法判定上限（自动换措辞重试）", False,
                  f"completion_tokens={completion}, finish={r.finish_reason}", soft=True)

    # 两次均提前 stop：无法判定（不构成上限不足的证据）
    pytest.skip(
        "默认上限无法判定：两次计数尝试模型均提前 stop "
        f"(completion_tokens={[a['completion_tokens'] for a in attempts]})。"
        "模型提前收尾 ≠ 上限不足；建议人工确认供应商默认上限或请其提供证明。"
    )


def test_31_02_显式131072被接受(client, rec):
    """max_tokens：显式传官方默认值 131072 被接受（2xx）"""
    req = {"model": client.model, "max_tokens": _OFFICIAL_DEFAULT_MAX_TOKENS,
           "messages": [{"role": "user", "content": "用一句话介绍北京。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_31_02_显式小于131072正常响应(client, rec):
    """max_tokens：显式传 65536（<131072）应正常响应（2xx）"""
    req = {"model": client.model, "max_tokens": 65536,
           "messages": [{"role": "user", "content": "用一句话介绍北京。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_31_02_显式131073在最大可设置内被接受(client, rec):
    """max_tokens：显式传 131073（>默认 131072，但在官方最大可设置 1048576 内）被接受（2xx）"""
    req = {"model": client.model, "max_tokens": _OFFICIAL_DEFAULT_MAX_TOKENS + 1,
           "messages": [{"role": "user", "content": "用一句话介绍北京。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_31_02_显式小值64精确生效(client, rec):
    """max_tokens：显式传小值 64 精确生效（completion≤64 且 finish=length，允许用户修改）"""
    req = {"model": client.model, "max_tokens": 64,
           "messages": [{"role": "user", "content": "请写一篇关于人工智能的长文，尽可能长。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r, require_content=False)
    completion = int((r.usage or {}).get("completion_tokens") or 0)
    rec.expect("completion_tokens ≤ 64 且 >0", 0 < completion <= 64,
               f"completion_tokens={completion}")
    rec.expect("finish_reason=length", r.finish_reason == "length",
               f"finish_reason={r.finish_reason!r}")
