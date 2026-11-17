"""条目#7 Token 统计分类（暂不实现 — 报告中以 SKIPPED 占位标注）。

原始要求：
- 工程验收表 #7：Token statistics must support categorization by model_id
  （用途：月度/季度对账）；
- 上线前条件 #8.b（完整版）：Token statistics support categorization by
  model_id, text chat, image chat, text claw, and image claw。

本条目为功能性验收，无附件用例文件。阻塞依赖：**供应商 token 统计/对账
查询接口的方式与文档**（按维度分类的用量如何查询——统计 API、账单导出
或管理后台口径），获取前无法闭环。

拟定验收思路（接口明确后实现）：
1. 流量制备（可复用 stress/core/scenarios.py 的四类场景构造）：
   分别发送已知请求数与 token 量的五类流量——
   指定 model_id 的 text chat（纯文本问答）、image chat（图片问答）、
   text claw（纯文本 agent 工具调用，不带图）、image claw（带图 agent 工具调用）；
2. 通过供应商统计接口查询用量；
3. 核对统计值：总量准确 + 按 model_id / text chat / image chat /
   text claw / image claw 五个维度正确分类隔离（各类互不串计）。
"""

from __future__ import annotations

import pytest


def test_07_token_statistics_pending(rec):
    """条目#7 Token 统计分类（model_id/text chat/image chat/text claw/image claw）"""
    pytest.skip(
        "条目#7 暂不实现：需供应商提供 token 统计/对账查询接口的方式与文档"
        "（五个维度分类用量如何查询）；接口明确后，发送已知量的"
        " text chat / image chat / text claw / image claw 四类流量，"
        "比对统计接口的分类数值实现验收"
    )
