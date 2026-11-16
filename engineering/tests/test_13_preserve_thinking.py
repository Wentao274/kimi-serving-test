"""补充条目（上线前条件第 9 条）Preserve thinking（经 KVV 单独测试 —
报告中以 SKIPPED 占位标注）。

原始要求：thinking:{type:enabled, keep:all} 时保留全部历史思考；
验证锚点：指定请求 prompt tokens=160，响应含与请求完全一致的 5 个数字。
经 KVV 单独测试；当前 KVV 未含 preserve-thinking 用例，需 Kimi 团队补充。
"""

from __future__ import annotations

import pytest


def test_13_preserve_thinking_pending(rec):
    """补充条目 Preserve thinking（经 KVV 单独测试，自研不实现）"""
    pytest.skip(
        "补充条目（上线前#9）Preserve thinking 经 KVV 单独测试，自研脚本不实现；"
        "当前 KVV 未含 preserve-thinking 用例"
        "（KVV README 声明 interleaved/preserved-thinking cases not migrated），"
        "需 Kimi 团队补充用例后执行"
    )
