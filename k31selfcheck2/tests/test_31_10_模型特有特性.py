"""3.1 模型特有特性：kimi-k3.1-pro 特有参数探针（对齐官方）。

- thinking.keep=all：Preserve Thinking（保留并回传历史 reasoning_content 参与上下文）；
- max_completion_tokens：OpenAI 新风格参数名，作为 max_tokens 别名兼容。
"""

from __future__ import annotations

from k31selfcheck2.tests._common import expect_common_ok, send

_MESSAGES = [{"role": "user", "content": "用一句话介绍杭州。"}]


def test_31_10_thinking_keep_all被接受(client, rec):
    """模型特有特性：thinking={type:enabled, keep=all}（Preserve Thinking）被接受且含 reasoning_content"""
    req = {"model": client.model, "messages": _MESSAGES, "max_tokens": 4096,
           "thinking": {"type": "enabled", "keep": "all"}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["reasoning_chars"] = len(r.reasoning_content or "")
    rec.expect("keep=all 下含 reasoning_content", bool(r.reasoning_content),
               f"reasoning_content 长度={len(r.reasoning_content or '')}")
    rec.check("Preserve Thinking 历史回传行为（多轮回传 reasoning_content）的完整验证超出本用例范围",
              True, "本用例仅覆盖参数接受", soft=True)


def test_31_10_max_completion_tokens兼容(client, rec):
    """模型特有特性：max_completion_tokens 作为 max_tokens 别名被接受且精确生效"""
    req = {"model": client.model, "messages": _MESSAGES, "max_completion_tokens": 64}
    r = send(client, rec, req)
    expect_common_ok(rec, r, require_content=False)
    completion = int((r.usage or {}).get("completion_tokens") or 0)
    rec.expect("max_completion_tokens=64 生效（completion ≤ 64 且 >0）",
               0 < completion <= 64, f"completion_tokens={completion}")
