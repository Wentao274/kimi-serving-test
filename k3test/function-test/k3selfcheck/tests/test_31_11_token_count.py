"""3.1 Token计数：相同的输入词组和官方模型输出的 token 数量对齐。"""

from __future__ import annotations

import pytest

from k3selfcheck.tests._common import expect_common_ok, send

_TEXT = "人工智能正在改变世界。请用三句话介绍机器学习、深度学习与大语言模型之间的关系。"


def test_31_11_与官方prompt_tokens对齐(client, official_client, rec):
    """Token计数：同一 text 请求打供应商与官方，usage.prompt_tokens 绝对计数一致（容差 ≤3）"""
    if official_client is None:
        pytest.skip("官方端点未配置（--official-base-url/--official-api-key/--official-model），跳过对照")
    req = {"model": client.model, "max_tokens": 16,
           "messages": [{"role": "user", "content": _TEXT}]}
    rv = send(client, rec, req)
    expect_common_ok(rec, rv, require_content=False)

    req_official = dict(req, model=official_client.model)
    ro = official_client.chat(req_official)
    rec.extra["official"] = {"model": official_client.model, "status_code": ro.status_code,
                              "error": ro.error, "usage": ro.usage}
    rec.expect("官方请求 HTTP 2xx", ro.ok, f"status={ro.status_code} err={ro.error}")

    vp = (rv.usage or {}).get("prompt_tokens")
    op = (ro.usage or {}).get("prompt_tokens")
    diff = abs(int(vp) - int(op)) if (vp is not None and op is not None) else None
    rec.extra["prompt_tokens_diff"] = diff
    rec.expect("usage.prompt_tokens 与官方一致（容差 ≤3）",
               diff is not None and diff <= 3,
               f"vendor={vp} official={op} diff={diff}")
