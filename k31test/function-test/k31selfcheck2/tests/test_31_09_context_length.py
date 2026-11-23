"""3.1 模型上下文长度：和官方模型对齐（kimi-k3.1-pro 1M 上下文 / 最大输出 131072）。"""

from __future__ import annotations

import pytest

from k31selfcheck2.tests._common import expect_common_ok, make_long_text, send

_LONG_PROMPT = make_long_text(130_000)
_LONG_1M_PROMPT = make_long_text(3_000_000)  # 约 1M+ tokens


def test_31_09_约130k字符长上下文(client, rec):
    """模型上下文长度：发送 ~130k 字符长 prompt（约 32k+ tokens）应 2xx（验证长上下文接入）"""
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content":
                         "请阅读以下长文并用一句话概括其主题。\n\n" + _LONG_PROMPT}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["prompt_chars"] = len(req["messages"][0]["content"])
    rec.expect("usage.prompt_tokens 反映长上下文输入（>10000）",
               int((r.usage or {}).get("prompt_tokens") or 0) > 10000,
               f"prompt_tokens={(r.usage or {}).get('prompt_tokens')}")


@pytest.mark.heavy
def test_31_09_约1M上下文长度heavy(client, rec, settings):
    """模型上下文长度：~3MB 字符长 prompt（约 1M tokens）应 2xx 且 usage.prompt_tokens ≥ 900k
    （验证官方 1M 上下文接入；Prefill 耗时数分钟，需 --include-heavy）"""
    if not settings.include_heavy:
        pytest.skip("需 --include-heavy 运行（~1M tokens 长上下文，Prefill 耗时数分钟）")
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content":
                         "请阅读以下长文并用一句话概括其主题。\n\n" + _LONG_1M_PROMPT}]}
    r = send(client, rec, req, timeout=1800)
    expect_common_ok(rec, r)
    rec.extra["prompt_chars"] = len(req["messages"][0]["content"])
    pt = int((r.usage or {}).get("prompt_tokens") or 0)
    rec.expect("usage.prompt_tokens ≥ 900k（约 1M 上下文被完整接受，未被截断）",
               pt >= 900_000, f"prompt_tokens={pt}")


def test_31_09_显式max_tokens_131072被接受(client, rec):
    """模型上下文长度：显式 max_tokens=131072（128K）被接受"""
    req = {"model": client.model, "max_tokens": 131072,
           "messages": [{"role": "user", "content": "用一句话介绍上海。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
