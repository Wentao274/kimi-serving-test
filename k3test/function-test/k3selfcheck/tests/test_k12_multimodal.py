"""检查项#12 图片/视频与多模态。

按 K3.1-Pro Chat 视觉契约验证：messages[].content[].image_url 对象数组 +
base64 data URL（原厂不支持公网图片 URL，推荐 base64）。本地用 Pillow 生成
96x96 PNG，文本提问"描述图片"，须使用依赖图片内容的语义检查：2xx 且 content
非空（硬），颜色语义命中（soft）。
"""

from __future__ import annotations

import base64
import io

from PIL import Image


def _make_data_url() -> str:
    img = Image.new("RGB", (96, 96), (220, 30, 30))  # 纯红 96x96
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def test_k12_image_base64_chat(client, rec):
    """Chat 多模态：base64 小图 + 文本提问 → 2xx 且 content 非空，颜色语义（soft）"""
    data_url = _make_data_url()
    req = {
        "model": client.model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "这张图片的主体是什么颜色？请用一个词回答。"},
            ],
        }],
        "max_completion_tokens": 4096,
    }
    r = client.chat(req)
    # 请求体中的 data URL 截断后再入报告，避免超大 body
    report_req = dict(req)
    report_req["messages"] = [{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": data_url[:64] + f"...<truncated,total={len(data_url)}chars>"}},
            {"type": "text", "text": "这张图片的主体是什么颜色？请用一个词回答。"},
        ],
    }]
    rec.attach_result(report_req, r, client.chat_completions_url, client.masked_headers())
    rec.extra["image"] = {"size": "96x96", "format": "PNG", "color": "red(220,30,30)",
                          "data_url_chars": len(data_url)}
    rec.expect("多模态请求 HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    rec.expect("content 非空（对图片作出了回答）", bool(r.content),
               f"content[:120]={r.content[:120]!r}")
    rec.check("颜色语义命中（红/red，依赖图片内容的语义检查）",
              ("红" in r.content) or ("red" in r.content.lower()),
              f"content[:120]={r.content[:120]!r}", soft=True)
