"""补充条目（上线前条件第 9 条）Preserve thinking 验证场景。

原始要求：thinking:{type:enabled, keep:all} 时保留全部历史思考
（Coding Agent、Claw 场景下保留历史推理有益）。

验证锚点（需求文档给定的请求与判定）：
- usage.prompt_tokens == 160——证明历史 reasoning_content 被完整保留进上下文；
- 响应包含与请求中完全一致的 5 个数字（473, 921, 235, 215, 222）——
  模型能看到自己上一轮的完整思考。

补充对照：不传 keep 字段时的 prompt_tokens 行为（soft，用于观察供应商
默认丢弃/保留口径）。

说明：KVV 当前未含 preserve-thinking 用例（其 README 声明 interleaved/
preserved-thinking cases not migrated），本场景为自研实现，与 KVV 后续
补充用例互补。
"""

from __future__ import annotations

EXPECTED_NUMBERS = ["473", "921", "235", "215", "222"]
EXPECTED_PROMPT_TOKENS = 160


def _request(model: str, keep: str | None = "all") -> dict:
    thinking: dict = {"type": "enabled"}
    if keep is not None:
        thinking["keep"] = keep
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": "随机告诉我三个数"},
            {
                "role": "assistant",
                "reasoning_content": "我先列5个数: 473, 921, 235, 215, 222，告诉用户前三个",
                "content": "473, 921, 235",
            },
            {"role": "user", "content": "告诉我你上一轮的思考过程"},
        ],
        "thinking": thinking,
        "max_tokens": 10240,
    }


def test_13_preserve_thinking_validation(client, rec):
    """preserve thinking 锚点：prompt_tokens == 160 且 5 个数字完全一致"""
    req = _request(client.model, keep="all")
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")

    pt = result.usage.get("prompt_tokens")
    rec.expect(f"usage.prompt_tokens == {EXPECTED_PROMPT_TOKENS}（历史 reasoning_content 被保留）",
               pt == EXPECTED_PROMPT_TOKENS,
               f"actual={pt}（≠{EXPECTED_PROMPT_TOKENS} 表示历史思考未按 keep=all 保留或口径不一致）")

    content = result.content or ""
    missing = [n for n in EXPECTED_NUMBERS if n not in content]
    rec.expect("响应含全部 5 个数字且完全一致", not missing,
               f"missing={missing}; content[:200]={content[:200]!r}")


def test_13_preserve_thinking_contrast(client, rec):
    """对照（soft）：不传 keep 字段时的 prompt_tokens 行为（观察默认丢弃/保留口径）"""
    req = _request(client.model, keep=None)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    pt = result.usage.get("prompt_tokens")
    rec.check(f"不传 keep 时 prompt_tokens ≠ {EXPECTED_PROMPT_TOKENS}（默认丢弃历史思考的对照）",
              pt != EXPECTED_PROMPT_TOKENS,
              f"actual={pt}（=160 表示该供应商默认也保留；≠160 表示默认丢弃）", soft=True)
