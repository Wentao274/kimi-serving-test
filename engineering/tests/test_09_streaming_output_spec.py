"""条目#9 Streaming Output Spec P0/P1（暂不实现 — 报告中以 SKIPPED 占位标注）。

原始要求（工程验收表）：支持《Streaming Output Spec List for Vendor (EN)》
中的 P0 和 P1 要求，并通过测试。
待获取该规范文档后按 P0/P1 条目逐条编写用例。
"""

from __future__ import annotations

import pytest


def test_09_streaming_output_spec_pending(rec):
    """条目#9 Streaming Output Spec P0/P1（待规范文档）"""
    pytest.skip(
        "条目#9 暂不实现：需获取《Streaming Output Spec List for Vendor (EN)》"
        "规范文档，获取后按 P0/P1 条目逐条编写用例"
    )
