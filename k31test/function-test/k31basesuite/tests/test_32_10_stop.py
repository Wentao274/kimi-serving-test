"""3.2 stop：单个/多个停止词、特殊字符停止词、空值处理。"""

from __future__ import annotations

from k31basesuite.tests._common import (error_body, error_message,
                                          expect_common_ok, send)


def test_32_10_单个停止词(client, rec):
    """stop：单个停止词（"STOP"）——输出应在停止词前截断"""
    req = {"model": client.model, "max_tokens": 2048, "stop": ["STOP"],
           "messages": [{"role": "user", "content":
                         "请原样输出以下内容，不要添加任何其他文字：BEGIN STOP END"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.expect("输出不包含停止词 STOP", "STOP" not in (r.content or ""),
               f"content={r.content!r}")
    rec.check("finish_reason=stop（停止词触发）", r.finish_reason == "stop",
              f"finish_reason={r.finish_reason!r}", soft=True)


def test_32_10_多个停止词数组(client, rec):
    """stop：多个停止词数组——输出应在任一停止词前截断"""
    req = {"model": client.model, "max_tokens": 2048, "stop": ["香蕉", "西瓜"],
           "messages": [{"role": "user", "content":
                         "请原样输出：苹果 香蕉 橘子 西瓜（不要输出其他内容）"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.expect("输出不包含任一停止词（香蕉/西瓜）",
               "香蕉" not in (r.content or "") and "西瓜" not in (r.content or ""),
               f"content={r.content!r}")


def test_32_10_特殊字符停止词(client, rec):
    r"""stop：特殊字符停止词（含 \n）——输出应在换行前截断"""
    req = {"model": client.model, "max_tokens": 2048, "stop": ["\n"],
           "messages": [{"role": "user", "content":
                         "请输出三行，每行一个词：第一行写苹果，第二行写香蕉，第三行写橘子。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.expect("输出不包含换行符（\\n 停止词生效）", "\n" not in (r.content or ""),
               f"content={r.content!r}")


def test_32_10_空stop值(client, rec):
    """stop：空 stop 值（记录行为）"""
    req = {"model": client.model, "max_tokens": 2048, "stop": [],
           "messages": [{"role": "user", "content": "用一句话介绍武汉。"}]}
    r = send(client, rec, req)
    if r.ok:
        expect_common_ok(rec, r)
        rec.check("stop=[] 空值被接受（正常生成）", True, "2xx", soft=True)
    else:
        rec.check("stop=[] 空值被拒绝（4xx 亦属合法，行为已记录）",
                  400 <= (r.status_code or 0) < 500,
                  f"status={r.status_code} msg={error_message(error_body(r))[:150]!r}",
                  soft=True)
