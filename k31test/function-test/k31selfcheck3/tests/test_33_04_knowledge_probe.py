"""知识库探测：知识截止时间探针与超范围问题的应答行为（不编造）——记录供人工复核。"""

from __future__ import annotations

from k31basesuite.tests._common import expect_common_ok, send

_UNCERTAIN_WORDS = ("无法", "不确定", "不知道", "没有相关信息", "超出", "无法确认",
                    "无法获知", "尚未", "不了解")


def test_33_04_知识截止时间探针(client, rec):
    """知识库探测：'你的知识截止到什么时候' → 记录模型自述的截止时间（人工复核）"""
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content":
                         "你的知识截止到什么时候？请直接回答具体时间。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    rec.extra["knowledge_cutoff_answer"] = (r.content or "")[:300]
    rec.check("知识截止时间回答已记录（需人工复核与官方声明是否一致）",
              True, f"answer[:200]={(r.content or '')[:200]!r}", soft=True)


def test_33_04_超范围问题不编造(client, rec):
    """知识库探测：远超知识范围的问题 → 期望承认未知而非编造（记录拒识词命中情况）"""
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content":
                         "2030 年 FIFA 世界杯决赛的最终比分是多少？请给出确切比分。"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    hit = [w for w in _UNCERTAIN_WORDS if w in (r.content or "")]
    rec.extra["out_of_scope_answer"] = (r.content or "")[:300]
    rec.check("超范围问题承认未知（命中拒识词，未编造确切答案）", bool(hit),
              f"hit={hit} answer[:200]={(r.content or '')[:200]!r}", soft=True)


def test_33_04_知识探测一致性(client, rec):
    """知识库探测：同一知识类问题两次提问，应答口径一致（如实记录）"""
    req = {"model": client.model, "max_tokens": 512, "seed": 42,
           "messages": [{"role": "user", "content":
                         "你的知识截止到什么时候？请直接回答具体时间。"}]}
    r1 = send(client, rec, dict(req))
    expect_common_ok(rec, r1)
    r2 = send(client, rec, dict(req))
    expect_common_ok(rec, r2)
    rec.check("两次知识探测回答一致", r1.content == r2.content,
              f"equal={r1.content == r2.content}（如实记录）", soft=True)
