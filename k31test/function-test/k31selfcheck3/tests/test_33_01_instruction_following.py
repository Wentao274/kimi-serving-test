"""指令遵循：格式/长度/关键词约束类指令应被严格遵循（IFEval 风格，程序化可判定）。"""

from __future__ import annotations

import json
import re

from k31basesuite.tests._common import expect_common_ok, send


def test_33_01_格式约束JSON输出(client, rec):
    """指令遵循：'用 JSON 格式回答，包含 name/age 字段，不要输出其他内容' → 输出可解析且含指定字段"""
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content":
                         "用 JSON 格式回答，必须包含 name 和 age 两个字段，不要输出任何其他内容。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    ok = False
    try:
        obj = json.loads(r.content)
        ok = isinstance(obj, dict) and "name" in obj and "age" in obj
    except (json.JSONDecodeError, TypeError):
        pass
    rec.expect("输出为含 name/age 字段的合法 JSON（格式约束被遵循）", ok,
               f"content[:200]={(r.content or '')[:200]!r}")


def test_33_01_格式约束项目符号列表(client, rec):
    """指令遵循：'用项目符号列出 3 个要点' → 输出含 ≥3 个列表项"""
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content":
                         "用项目符号列出 3 个要点介绍人工智能的应用领域，每行一个要点。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    bullets = [l for l in (r.content or "").splitlines()
               if re.match(r"^\s*[-*•·]\s+\S|^\s*\d+[.、)]\s*\S", l)]
    rec.expect("输出含 ≥3 个列表项（列表约束被遵循）", len(bullets) >= 3,
               f"bullets={len(bullets)} content[:200]={(r.content or '')[:200]!r}")


def test_33_01_长度约束不超过10字(client, rec):
    """指令遵循：'用不超过 10 个字回答' → 输出长度 ≤ 15 字符（含标点容差）"""
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content":
                         "中国的首都是哪里？请用不超过 10 个字回答。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    length = len((r.content or "").strip())
    rec.expect("输出 ≤15 字符（长度约束被遵循，含标点容差）", 0 < length <= 15,
               f"len={length} content={r.content!r}")


def test_33_01_关键词约束必含(client, rec):
    """指令遵循：'回答中必须包含“西湖”二字' → 输出含指定关键词"""
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content":
                         "用一句话介绍杭州，回答中必须包含“西湖”二字。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.expect("输出含必含关键词“西湖”（必含约束被遵循）", "西湖" in (r.content or ""),
               f"content[:200]={(r.content or '')[:200]!r}")


def test_33_01_关键词约束禁止(client, rec):
    """指令遵循：'回答中不要出现“苹果”二字' → 输出不含禁用词"""
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content":
                         "介绍三种常见水果，回答中不要出现“苹果”二字。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.expect("输出不含禁用词“苹果”（禁用约束被遵循）", "苹果" not in (r.content or ""),
               f"content[:200]={(r.content or '')[:200]!r}")
