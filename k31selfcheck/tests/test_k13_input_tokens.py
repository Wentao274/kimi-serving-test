"""检查项#13 输入 Token 专项对齐。

同协议、同有效输入对照供应商与官方：比较 usage.prompt_tokens 绝对计数一致
（容差 ±3）。官方未配置时 skipped。覆盖纯 text chat 与带 system 的请求。
不要求随机生成的输出 Token 一律相同。
"""

from __future__ import annotations

import pytest

_TOLERANCE = 3

_TEXT_MESSAGES = [{"role": "user", "content": "请用三句话介绍杭州。"}]
_SYSTEM_MESSAGES = [
    {"role": "system", "content": "你是一名严谨的中文技术写作助手，回答控制在两句话以内。"},
    {"role": "user", "content": "什么是流式响应？"},
]


def _run_pair(client, official_client, rec, messages, label: str) -> None:
    req = {"model": client.model, "messages": messages, "max_completion_tokens": 1024}
    rv = client.chat(req)
    rec.attach_result(req, rv, client.chat_completions_url, client.masked_headers())
    rec.expect(f"{label} 供应商 HTTP 2xx", rv.ok,
               f"status={rv.status_code} err={rv.error}")
    v_pt = (rv.usage or {}).get("prompt_tokens")
    rec.expect(f"{label} 供应商 usage.prompt_tokens 为整数",
               isinstance(v_pt, int), f"prompt_tokens={v_pt!r}")

    req_o = dict(req, model=official_client.model)
    ro = official_client.chat(req_o)
    rec.extra["official"] = {
        "model": official_client.model,
        "status": ro.status_code,
        "usage": ro.usage,
        "prompt_tokens": (ro.usage or {}).get("prompt_tokens"),
    }
    rec.expect(f"{label} 官方 HTTP 2xx", ro.ok,
               f"status={ro.status_code} err={ro.error}")
    o_pt = (ro.usage or {}).get("prompt_tokens")
    rec.expect(f"{label} 官方 usage.prompt_tokens 为整数",
               isinstance(o_pt, int), f"prompt_tokens={o_pt!r}")

    diff = abs(v_pt - o_pt)
    rec.expect(f"{label} prompt_tokens 绝对计数一致（容差 ±{_TOLERANCE}）",
               diff <= _TOLERANCE,
               f"vendor={v_pt} official={o_pt} diff={diff}")


def test_k13_text_chat_prompt_tokens(client, official_client, rec):
    """纯 text chat：供应商 vs 官方 usage.prompt_tokens 对齐（±3）"""
    if official_client is None:
        pytest.skip("官方对照未配置（--official-base-url/--official-api-key/--official-model）")
    _run_pair(client, official_client, rec, _TEXT_MESSAGES, "text chat")


def test_k13_system_prompt_tokens(client, official_client, rec):
    """带 system 的请求：供应商 vs 官方 usage.prompt_tokens 对齐（±3）"""
    if official_client is None:
        pytest.skip("官方对照未配置（--official-base-url/--official-api-key/--official-model）")
    _run_pair(client, official_client, rec, _SYSTEM_MESSAGES, "system+user")
