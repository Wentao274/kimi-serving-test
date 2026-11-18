"""条目#2（工程验收表）参数默认值和官方保持一致。

原始要求（工程验收表）：
  默认值和官方保持一致；默认开 thinking；
  temperature：默认 1.0，修改为其他值需返回 HTTP 400。
  Parameter defaults must match the official defaults. Thinking is enabled
  by default; temperature is 1.0. An error must be returned if the value
  is out of range.

  默认值表（上线前条件第 3 条）：
  thinking 模式：temperature=1.0, top_p=0.95, presence_penalty=0, frequency_penalty=0, n=1
  disabled 模式：temperature=0.6，其余相同

校验逻辑：
1. 不传采样参数的请求必须成功（两种 thinking 模式）；
2. 显式传官方默认值必须被接受；
3. 无参请求与显式默认值请求的 logprobs 分布指纹应一致（行为等价）；
4. 传非官方默认值必须返回 HTTP 4xx（硬校验，依据工程验收表 temperature 条款，
   其余参数按"默认值和官方保持一致"同一原则判定）。
"""

from __future__ import annotations

import pytest

THINKING_DEFAULTS = {
    "temperature": 1.0,
    "top_p": 0.95,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "n": 1,
}
NON_THINKING_DEFAULTS = {**THINKING_DEFAULTS, "temperature": 0.6}

# 各参数的非官方值（应被拒绝，HTTP 4xx）
NON_DEFAULT_VALUES = [
    ("temperature", 2.0),
    ("temperature", 0.3),
    ("top_p", 0.8),
    ("presence_penalty", 0.5),
    ("frequency_penalty", 0.5),
    ("n", 2),
]

_PROMPT = [{"role": "user", "content": "Say 'OK' and nothing else."}]


def _req(model: str, thinking_enabled: bool, extra: dict | None = None) -> dict:
    req = {
        "model": model,
        "messages": _PROMPT,
        "max_tokens": 32,
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }
    if extra:
        req.update(extra)
    return req


def _defaults_for(thinking_enabled: bool) -> dict:
    return THINKING_DEFAULTS if thinking_enabled else NON_THINKING_DEFAULTS


@pytest.mark.parametrize("thinking_enabled", [True, False], ids=["thinking", "non-thinking"])
def test_02_no_param_succeeds(client, rec, thinking_enabled):
    """不传任何可选采样参数，请求应成功"""
    req = _req(client.model, thinking_enabled)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")


@pytest.mark.parametrize("param_name", list(THINKING_DEFAULTS), ids=lambda p: f"param={p}")
@pytest.mark.parametrize("thinking_enabled", [True, False], ids=["thinking", "non-thinking"])
def test_02_default_param_accepted(client, rec, param_name, thinking_enabled):
    """显式传官方默认值应被接受"""
    value = _defaults_for(thinking_enabled)[param_name]
    req = _req(client.model, thinking_enabled, {param_name: value})
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect(f"{param_name}={value} 被接受（HTTP 2xx）", result.ok,
               f"status={result.status_code} err={result.error}")


def _extract_top_logprobs(result) -> list | None:
    """从非流式响应中提取首 token 的 top_logprobs；不支持则返回 None。"""
    data = result.response_json or {}
    choices = data.get("choices") or []
    if not choices:
        return None
    logprobs = (choices[0].get("logprobs") or {})
    content = logprobs.get("content") or []
    if not content:
        return None
    return content[0].get("top_logprobs") or None


@pytest.mark.parametrize("thinking_enabled", [True, False], ids=["thinking", "non-thinking"])
def test_02_default_equivalence_logprobs(client, rec, thinking_enabled):
    """无参请求 vs 显式官方默认值：logprobs 分布指纹应一致（行为等价对照）。

    logprobs 反映模型输出分布，不依赖采样随机性。需要端点支持
    logprobs/top_logprobs；不支持则跳过。
    """
    mode_name = "thinking" if thinking_enabled else "non-thinking"
    defaults = _defaults_for(thinking_enabled)
    base = {
        "model": client.model,
        "messages": _PROMPT,
        "max_tokens": 1,
        "logprobs": True,
        "top_logprobs": 5,
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }
    req_implicit = dict(base)
    req_explicit = {**base, **defaults}

    res_implicit = client.chat(req_implicit)
    rec.attach_result(req_implicit, res_implicit, client.chat_completions_url, client.masked_headers())
    rec.expect("无参请求 HTTP 2xx", res_implicit.ok,
               f"status={res_implicit.status_code} err={res_implicit.error}")

    res_explicit = client.chat(req_explicit)
    rec.expect("显式默认值请求 HTTP 2xx", res_explicit.ok,
               f"status={res_explicit.status_code} err={res_explicit.error}")

    lp_implicit = _extract_top_logprobs(res_implicit)
    lp_explicit = _extract_top_logprobs(res_explicit)
    if lp_implicit is None or lp_explicit is None:
        rec.check("供应商端点返回 logprobs", False,
                  f"供应商({client.model}) 响应中无 logprobs 字段", soft=True)
        pytest.skip(f"供应商({client.model}) 不支持 logprobs，无法做分布指纹对照")

    rec.extra[f"{mode_name}_implicit_top_logprobs"] = lp_implicit
    rec.extra[f"{mode_name}_explicit_top_logprobs"] = lp_explicit

    tokens_i = [t.get("token") for t in lp_implicit]
    tokens_e = [t.get("token") for t in lp_explicit]
    rec.expect("无参 ≡ 显式默认：top_logprobs token 序列一致", tokens_i == tokens_e,
               f"implicit={tokens_i} vs explicit={tokens_e}")

    max_diff = 0.0
    for ti, te in zip(lp_implicit, lp_explicit):
        if ti.get("token") == te.get("token"):
            max_diff = max(max_diff, abs((ti.get("logprob") or 0) - (te.get("logprob") or 0)))
    rec.check("无参 ≡ 显式默认：logprob 数值偏差 <= 0.05", max_diff <= 0.05,
              f"max_diff={max_diff:.6f}（数值抖动容忍）", soft=True)


@pytest.mark.parametrize("param_name,value", NON_DEFAULT_VALUES,
                         ids=[f"{n}={v}" for n, v in NON_DEFAULT_VALUES])
@pytest.mark.parametrize("thinking_enabled", [True, False], ids=["thinking", "non-thinking"])
def test_02_non_default_param_rejected(client, rec, param_name, value, thinking_enabled):
    """非官方默认值必须返回 HTTP 4xx（工程验收表 temperature 条款）"""
    default = _defaults_for(thinking_enabled)[param_name]
    if value == default:
        pytest.skip(f"{param_name}={value} 恰为该模式官方默认值")
    req = _req(client.model, thinking_enabled, {param_name: value})
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect(f"{param_name}={value} 被拒绝（HTTP 4xx，默认={default}）",
               result.status_code is not None and 400 <= result.status_code < 500,
               f"status={result.status_code}")
