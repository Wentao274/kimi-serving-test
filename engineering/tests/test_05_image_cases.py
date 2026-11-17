"""条目#5 图片输入测试用例（25 条，附件回放）+ 图片格式覆盖（7 种）。

原始要求：供应商应能够跑通如下测试用例，覆盖多个维度——
不同的 image_url 格式（字符串 vs {"url": ...} 对象）、不同的 finish_reason
（stop vs tool_calls）、image_url 位于 role=user 或 role=tool 的消息中、
支持最多 1000 张图片、支持 jpeg/png/gif/tiff/bmp/webp/heic 格式。

数据源：engineering/data/vendor-img-testcases-inhouse-3.jsonl
  每行 {"expected_finish_reason": "stop"|"tool_calls", "transformed_request": {...}}

回放策略：
- 每条用例按其原生 stream 配置运行一次（native）；
- 每条用例再以翻转 stream 模式运行一次（flipped），验证流式/非流式兼容；
  case25（1000 张图）的 flipped 模式成本高，需 --include-heavy 才运行；
- 校验 HTTP 2xx + finish_reason 与期望一致 + tool_calls 结构合法。

格式覆盖说明：附件图片全部来自 blobproxy（URL 无格式标记），不覆盖格式维度；
图片格式（jpeg/png/gif/tiff/bmp/webp/heic）由 test_05_image_formats 以本地
生成的小图（base64 data URL，免图床依赖）逐格式验证供应商解码能力。

注意：附件图片 URL 有效期至 2027-03-18，过期后需替换图床。
"""

from __future__ import annotations

import json

import pytest

from engineering.core.data import load_image_cases

_CASES = load_image_cases()


def _count_images(request: dict) -> int:
    n = 0
    for m in request.get("messages", []):
        content = m.get("content")
        if isinstance(content, list):
            n += sum(1 for p in content
                     if isinstance(p, dict) and p.get("type") == "image_url")
    return n


def _build_params():
    params = []
    for idx, row in enumerate(_CASES, start=1):
        params.append((idx, "native"))
        params.append((idx, "flipped"))   # 大体积用例的 flipped 运行时按 --include-heavy 控制
    return params


_PARAMS = _build_params()
_IDS = [f"case{i:02d}-{mode}" for i, mode in _PARAMS]


def _valid_tool_calls(tool_calls: list) -> tuple[bool, str]:
    if not tool_calls:
        return False, "tool_calls 为空"
    for tc in tool_calls:
        fn = (tc or {}).get("function") or {}
        if not fn.get("name"):
            return False, f"tool_call 缺少 function.name: {tc}"
        args = fn.get("arguments", "")
        if isinstance(args, str):
            try:
                json.loads(args) if args else None
            except json.JSONDecodeError as exc:
                return False, f"arguments 非合法 JSON: {exc}"
    return True, ""


@pytest.mark.parametrize("case_idx,mode", _PARAMS, ids=_IDS)
def test_05_image_case(client, rec, settings, case_idx, mode):
    """图片用例回放：finish_reason 与期望一致"""
    row = _CASES[case_idx - 1]
    expected = row["expected_finish_reason"]
    req = dict(row["transformed_request"])
    req["model"] = client.model
    native_stream = bool(req.get("stream", False))
    stream = native_stream if mode == "native" else not native_stream
    n_img = _count_images(req)
    if mode == "flipped" and n_img >= 100 and not settings.include_heavy:
        pytest.skip(f"case{case_idx} 含 {n_img} 张图片，flipped 模式需 --include-heavy 运行")
    if stream:
        req["stream"] = True
        req.setdefault("stream_options", {"include_usage": True})
    else:
        req.pop("stream", None)
        req.pop("stream_options", None)

    rec.extra.update({
        "case_no": case_idx, "mode": mode, "images": n_img,
        "expected_finish_reason": expected, "stream": stream,
    })
    timeout = settings.timeout * 3 if n_img >= 100 else settings.timeout
    result = client.chat(req, timeout=timeout)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())

    rec.expect("HTTP 2xx", result.ok,
               f"status={result.status_code} err={result.error}")
    rec.expect(f"finish_reason == '{expected}'", result.finish_reason == expected,
               f"actual={result.finish_reason}")
    if expected == "tool_calls":
        ok, msg = _valid_tool_calls(result.tool_calls)
        rec.expect("tool_calls 结构合法", ok, msg)
    else:
        rec.expect("content 或 tool_calls 非空",
                   bool(result.content.strip()) or bool(result.tool_calls),
                   "响应消息为空")
    if stream:
        rec.expect("usage 非空（include_usage 生效）", bool(result.usage),
                   f"usage={result.usage}")


# ---------------------------------------------------------------- 图片格式覆盖
_FORMAT_SPECS = [
    ("jpeg", "JPEG", "image/jpeg"),
    ("png", "PNG", "image/png"),
    ("gif", "GIF", "image/gif"),
    ("tiff", "TIFF", "image/tiff"),
    ("bmp", "BMP", "image/bmp"),
    ("webp", "WEBP", "image/webp"),
    ("heic", "HEIF", "image/heic"),
]


def _make_image_data_url(pil_fmt: str, mime: str) -> str:
    """本地生成一张小测试图并编码为 data URL（不依赖外部图床）。"""
    import base64
    import io
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (96, 96), (30, 90, 160))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 16, 80, 80], fill=(220, 60, 60))
    d.rectangle([36, 36, 60, 60], fill=(240, 220, 60))
    if pil_fmt == "GIF":
        img = img.convert("P")
    if pil_fmt == "HEIF":
        import pillow_heif
        pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    img.save(buf, format=pil_fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:{mime};base64,{b64}"


@pytest.mark.parametrize("fmt_name,pil_fmt,mime", _FORMAT_SPECS,
                         ids=[s[0] for s in _FORMAT_SPECS])
def test_05_image_formats(client, rec, fmt_name, pil_fmt, mime):
    """图片格式支持：jpeg/png/gif/tiff/bmp/webp/heic（本地生成 base64 小图）"""
    try:
        data_url = _make_image_data_url(pil_fmt, mime)
    except Exception as exc:
        pytest.fail(f"本地生成 {fmt_name} 测试图失败（编码库缺失？pip install -r requirements.txt）: {exc}")
    req = {
        "model": client.model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "请用一句话描述这张图片。"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "max_tokens": 256,
        "thinking": {"type": "disabled"},
    }
    rec.extra["format"] = fmt_name
    result = client.chat(req)
    rec.attach_result(req, result, client.chat_completions_url, client.masked_headers())
    rec.expect(f"HTTP 2xx（{fmt_name} 格式被供应商解码）", result.ok,
               f"status={result.status_code} err={result.error}")
    rec.expect("content 非空（解码后有正常响应）", bool(result.content.strip()),
               f"content={result.content[:120]!r}")
