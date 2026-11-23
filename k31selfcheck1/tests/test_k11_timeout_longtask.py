"""检查项#11 超时与长任务。

保留原要求：模型单次请求最长返回时长 1 小时。
- 日常档：数分钟流式生成不断流（counting 到 2000，连接稳定、正常收尾）。
- heavy 档：网关读超时上限 1h 探测——max_tokens=131072 长流式，判定窗口
  3597~3603s：截于 1h 通过；<3597 因 cap 结束记 skipped 注明未触达；<3597
  断流失败；>3603 仍流失败。
秒级超时、短样本或参数预算上限不能证明 1 小时链路已验收。
"""

from __future__ import annotations

import pytest

_DAILY_MAX = 32768
_HEAVY_MAX = 131072
_WINDOW_LO = 3597.0
_WINDOW_HI = 3603.0


def test_k11_daily_stream_stability(client, rec):
    """日常档：数分钟流式生成不断流（counting 到 2000），连接稳定、正常收尾"""
    req = {"model": client.model,
           "messages": [{"role": "user",
                         "content": "从 1 数到 2000，每个数字一行，不要输出其他内容。"}],
           "max_completion_tokens": _DAILY_MAX, "stream": True}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.extra["n_chunks"] = r.n_chunks
    rec.expect("流式 HTTP 2xx 且连接未中断（无传输错误）", r.ok and not r.error,
               f"status={r.status_code} err={r.error} latency={r.latency_s:.1f}s")
    rec.expect("持续收到分片（n_chunks>100，非一次性返回）", r.n_chunks > 100,
               f"n_chunks={r.n_chunks}")
    rec.expect("正常收尾（finish_reason 非空）", bool(r.finish_reason),
               f"finish_reason={r.finish_reason!r}")
    rec.check("数到 2000（生成完整，soft）", "2000" in r.content,
              f"content_tail={r.content[-80:]!r}", soft=True)


@pytest.mark.heavy
def test_k11_heavy_one_hour_read_timeout(client, rec, settings):
    """heavy 档：网关读超时上限 1h 探测（max_tokens=131072 长流式，窗口 3597~3603s）"""
    if not settings.include_heavy:
        pytest.skip("重负载用例：需 --include-heavy 才运行")
    req = {"model": client.model,
           "messages": [{"role": "user",
                         "content": "从 1 开始逐行写整数，每行一个，尽可能多地写，不要停。"}],
           "max_completion_tokens": _HEAVY_MAX, "stream": True}
    # 读超时放宽到窗口之上，以便观察 >3603 仍流的行为
    r = client.chat(req, timeout=_WINDOW_HI + 180.0)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    t = r.latency_s
    rec.extra.update({"latency_s": round(t, 1), "n_chunks": r.n_chunks,
                      "window": [_WINDOW_LO, _WINDOW_HI],
                      "judge": "3597~3603s 截于1h通过；<3597 cap结束 skipped；"
                               "<3597 断流失败；>3603 仍流失败"})
    if r.error and t < _WINDOW_LO:
        rec.expect("1h 链路：3597s 前断流", False,
                   f"latency={t:.1f}s err={r.error}（断流失败）")
    elif _WINDOW_LO <= t <= _WINDOW_HI:
        rec.expect("1h 链路：流式截于 3597~3603s 窗口（1h 上限）", True,
                   f"latency={t:.1f}s finish={r.finish_reason!r}（截于 1h，通过）")
    elif t < _WINDOW_LO:
        rec.check("1h 链路：生成在 3597s 前结束", True,
                  f"latency={t:.1f}s finish={r.finish_reason!r}", soft=True)
        pytest.skip(f"生成于 {t:.1f}s 因输出预算/自然结束而收尾，未触达 1h 上限，"
                    "无法判定网关读超时")
    else:
        rec.expect("1h 链路：3603s 后流必须已结束", False,
                   f"latency={t:.1f}s err={r.error}（>3603s 仍在流，失败）")
