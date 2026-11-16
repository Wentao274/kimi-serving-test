"""条目#10 New Model Spec（K3.1 新功能）（暂不实现 — 报告中以 SKIPPED 占位标注）。

原始要求（工程验收表）：支持《New Model Spec List for Vendor》中的功能并通过测试。
待获取该规范文档后实现；preserve thinking 预计归属该范围（经 KVV 单独测试）。
"""

from __future__ import annotations

import pytest


def test_10_new_model_spec_pending(rec):
    """条目#10 New Model Spec（K3.1 新功能）（待规范文档）"""
    pytest.skip(
        "条目#10 暂不实现：需获取《New Model Spec List for Vendor》规范文档；"
        "preserve thinking 预计归属该范围，经 KVV 单独测试"
        "（当前 KVV 未含 preserve-thinking 用例，需 Kimi 团队补充）"
    )
