"""检查项#9 参数及输入边界。

覆盖必填缺失（空 messages → 4xx）、空字符串 content（4xx 或正常，如实记录实际
行为）、超大请求体（200KB 文本 → 应 2xx）与停止控制（Chat stop 数组被接受）。
参数探针只证明接受/拒绝，不以 HTTP 200 推定参数生效。
"""

from __future__ import annotations


def test_k09_empty_messages(client, rec):
    """空 messages 数组（必填缺失）→ 4xx，不得 200 放行"""
    req = {"model": client.model, "messages": [], "max_completion_tokens": 32}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("空 messages 被拒绝（4xx）",
               r.status_code is not None and 400 <= r.status_code < 500,
               f"status={r.status_code} err={r.error}")


def test_k09_empty_content(client, rec):
    """空字符串 content → 4xx 或正常，如实记录实际行为（soft）"""
    req = {"model": client.model, "messages": [{"role": "user", "content": ""}],
           "max_completion_tokens": 32}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    if r.ok:
        rec.check("空字符串 content 的实际行为", True,
                  "供应商接受空 content（HTTP 2xx），如实记录；"
                  f"finish={r.finish_reason!r}", soft=True)
    else:
        rec.check("空字符串 content 的实际行为",
                  r.status_code is not None and 400 <= r.status_code < 500,
                  f"供应商拒绝空 content：status={r.status_code} err={r.error}", soft=True)


def test_k09_oversize_content(client, rec):
    """超大 content（约 200KB 文本）→ 应 2xx（超大请求体可正常处理）"""
    big_text = "供应商自测基线输入边界验证。" * 10000  # ~ 200KB+ 中文文本
    rec.extra["content_bytes"] = len(big_text.encode("utf-8"))
    req = {"model": client.model,
           "messages": [{"role": "user", "content": big_text + "\n请只回复：收到"}],
           "max_completion_tokens": 1024}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("超大 content（~200KB）HTTP 2xx", r.ok,
               f"status={r.status_code} err={r.error} bytes={rec.extra['content_bytes']}")


def test_k09_stop_sequences(client, rec):
    """Chat stop 数组被接受且停止控制生效（输出在停止词前截断）"""
    req = {"model": client.model,
           "messages": [{"role": "user",
                         "content": "从 1 数到 20，每个数字一行，不要输出其他内容。"}],
           "max_completion_tokens": 4096, "stop": ["\n5"]}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("stop 数组被接受（HTTP 2xx）", r.ok,
               f"status={r.status_code} err={r.error}")
    rec.check("停止控制生效（content 不含停止词之后的数字 6）",
              "6" not in r.content,
              f"content[:200]={r.content[:200]!r} finish={r.finish_reason!r}；"
              "注：HTTP 200 仅证明参数被接受，本项核停止效果", soft=True)
    rec.check("停止后 finish_reason 为 stop（如实记录）", r.finish_reason == "stop",
              f"finish_reason={r.finish_reason!r}", soft=True)
