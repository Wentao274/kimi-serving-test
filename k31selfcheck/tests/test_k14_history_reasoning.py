"""检查项#14 消息历史与思考回填。

按原厂要求原样回传完整 assistant 消息：Chat 保留 messages[].reasoning_content。
多轮对话中 assistant 历史带 reasoning_content + thinking.keep=all 时，模型应能
复述上一轮思考中的指定信息。需求锚点：usage.prompt_tokens=160（证明历史
reasoning_content 被完整保留进上下文）；响应含与请求完全一致的 5 个数字
473, 921, 235, 215, 222（模型能看到自己上一轮的完整思考）。
"""

from __future__ import annotations

EXPECTED_NUMBERS = ["473", "921", "235", "215", "222"]
EXPECTED_PROMPT_TOKENS = 160


def _request(model: str) -> dict:
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
        "thinking": {"type": "enabled", "keep": "all"},
        "max_tokens": 10240,
    }


def test_k14_history_reasoning_keep_all(client, rec):
    """思考回填锚点：keep=all 时 prompt_tokens=160 且响应含完全一致的 5 个数字"""
    req = _request(client.model)
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")

    pt = (r.usage or {}).get("prompt_tokens")
    rec.expect(f"usage.prompt_tokens == {EXPECTED_PROMPT_TOKENS}"
               "（历史 reasoning_content 按 keep=all 完整保留进上下文）",
               pt == EXPECTED_PROMPT_TOKENS,
               f"actual={pt}（≠{EXPECTED_PROMPT_TOKENS} 表示历史思考未保留或口径不一致）")

    missing = [n for n in EXPECTED_NUMBERS if n not in (r.content or "")]
    rec.expect("响应含与请求完全一致的 5 个数字 473,921,235,215,222"
               "（模型能看到上一轮完整思考）",
               not missing,
               f"missing={missing}; content[:200]={(r.content or '')[:200]!r}")
