"""条目#8（工程验收表）X-Msh-ProviderDeployId 响应头。

原始要求（工程验收表）：
  在 response header 中支持 "X-Msh-ProviderDeployId": <deployment id> 字段，
  用于显示版本（breaking change 后版本变更可见）。
  Support "X-Msh-ProviderDeployId": <deployment id> in response headers,
  which will show us the version changed after breaking change.

校验：
- 常规请求与流式请求的响应头中均应包含 X-Msh-ProviderDeployId 且值非空（硬校验）。
"""

from __future__ import annotations

HEADER_NAME = "x-msh-providerdeployid"


def _minimal_req(model: str, stream: bool = False) -> dict:
    req = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK and nothing else."}],
        "max_tokens": 16,
    }
    if stream:
        req["stream"] = True
        req["stream_options"] = {"include_usage": True}
    return req


def _check_deploy_header(result, rec, stream_label: str) -> None:
    headers = {k.lower(): v for k, v in (result.response_headers or {}).items()}
    value = headers.get(HEADER_NAME, "")
    rec.expect(f"{stream_label}响应头包含 X-Msh-ProviderDeployId 且值非空",
               bool(value.strip()),
               f"值={value!r}" if value else f"响应头键={sorted(headers)[:20]}")


def test_08_provider_deploy_id_header(client, rec):
    """非流式：响应头应包含 X-Msh-ProviderDeployId"""
    req = _minimal_req(client.model)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    _check_deploy_header(result, rec, "非流式")


def test_08_provider_deploy_id_header_stream(client, rec):
    """流式：响应头应包含 X-Msh-ProviderDeployId"""
    req = _minimal_req(client.model, stream=True)
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", result.ok, f"status={result.status_code} err={result.error}")
    _check_deploy_header(result, rec, "流式")
