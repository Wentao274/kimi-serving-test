"""条目#7 Token 统计分类（暂不实现 — 报告中以 SKIPPED 占位标注）。

原始要求（工程验收表）：Token statistics must support categorization by model_id。
用途：月度/季度对账。

本条目为功能性验收，无附件用例文件。待供应商提供 token 统计/对账
查询接口的方式与文档后实现。拟定验收思路：
- 向指定 model_id 发送若干已知 token 量的请求；
- 通过供应商统计接口查询用量，核对统计值按 model_id 分类且数值准确；
- 若供应商服务多个 model_id，分别发送并核对分类隔离。
"""

from __future__ import annotations

import pytest


def test_07_token_statistics_pending(rec):
    """条目#7 Token 统计按 model_id 分类（待供应商统计接口文档）"""
    pytest.skip(
        "条目#7 暂不实现：需供应商提供 token 统计/对账查询接口的方式与文档"
        "（按 model_id 分类的用量如何查询）；接口明确后按已知 token 量请求"
        "比对统计值实现验收"
    )
