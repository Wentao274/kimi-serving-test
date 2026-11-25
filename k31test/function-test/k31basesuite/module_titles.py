"""套件模块名 → 中文标题（用于报告分组头展示；未映射时回退原模块名）。"""

from __future__ import annotations

MODULE_TITLES = {
    # ---- k31selfcheck1（K3.1-Pro 供应商自测基线 · 14 测试点）----
    "test_k01_protocols": "三协议与响应格式",
    "test_k02_usage_cache": "usage 与缓存计量",
    "test_k03_thinking_effort": "常驻思考与推理强度",
    "test_k04_sampling_budget": "采样与输出预算",
    "test_k05_stream_fsm": "流式状态机与完整性",
    "test_k06_structured_output": "结构化输出",
    "test_k07_tool_call_loop": "工具调用与多步闭环",
    "test_k08_error_codes": "错误码与异常响应",
    "test_k09_input_boundaries": "参数及输入边界",
    "test_k10_observability": "可观测性与复现证据",
    "test_k11_timeout_longtask": "超时与长任务",
    "test_k12_multimodal": "图片/视频与多模态",
    "test_k13_input_tokens": "输入 Token 专项对齐",
    "test_k14_history_reasoning": "消息历史与思考回填",
    # ---- k31selfcheck2 / k31basesuite（模型接入要求对外版 3.1/3.2）----
    "test_31_01_thinking": "Thinking控制",
    "test_31_02_max_tokens": "max_tokens（默认 131072）",
    "test_31_03_system_prompt": "System Prompt",
    "test_31_04_whitelist": "免审核白名单-关闭绿网",
    "test_31_05_rate_limit": "频控容忍",
    "test_31_06_cache": "Cache能力支持",
    "test_31_07_structured_output": "结构化输出",  # 与 k06 同测试点，合并展示
    "test_31_08_function_calling": "Function Calling/工具调用",
    "test_31_09_context_length": "模型上下文长度",
    "test_31_10_special_features": "模型特有特性",
    "test_31_11_token_count": "Token计数",
    "test_32_01_messages": "messages",
    "test_32_02_messages_elements": "messages-元素",
    "test_32_03_top_p": "top_p",
    "test_32_04_frequency_penalty": "frequency_penalty",
    "test_32_05_presence_penalty": "presence_penalty",
    "test_32_06_max_tokens": "max_tokens（边界值/思维链差异）",
    "test_32_07_input_length": "输入长度",
    "test_32_08_stream": "stream",
    "test_32_09_temperature": "temperature（思考模式温度控制）",
    "test_32_10_stop": "stop",
    "test_32_11_json_object": "json_object",
    "test_32_12_stream_options": "stream_options",
    "test_32_13_input_length_nonstream": "输入长度-非流式输出",
    "test_32_14_auth_security": "鉴权与安全",
    "test_32_15_encoding_special_chars": "编码与特殊字符",
    "test_32_16_system_prompt_behavior": "system prompt 行为",
    "test_32_17_idempotency": "幂等性验证",
    # ---- k31selfcheck3（功能与兼容性测试）----
    "test_33_01_instruction_following": "指令遵循",
    "test_33_02_orphan_tool_message": "孤儿 tool 消息校验",
    "test_33_03_response_consistency": "响应一致性校验",
    "test_33_04_knowledge_probe": "知识库探测",
    "test_33_05_safety_guardrail": "安全围栏校验",
    "test_33_06_timeout_exception": "超时与异常处理",
}


# 31_/32_ 共享模块 → 《Kimi-K3.1-Pro 供应商自测基线标准》功能兼容性要求 14 项
# （用于 k31selfcheck1 / k3selfcheck 报告分组；k31selfcheck2/k31basesuite 保持各自测试点名）
BASELINE14_TITLES = {
    # #2 usage 与缓存计量
    "test_31_06_cache": "usage 与缓存计量",
    # #3 常驻思考与推理强度
    "test_31_01_thinking": "常驻思考与推理强度",
    "test_31_10_special_features": "常驻思考与推理强度",
    # #4 采样与输出预算
    "test_31_02_max_tokens": "采样与输出预算",
    "test_32_03_top_p": "采样与输出预算",
    "test_32_04_frequency_penalty": "采样与输出预算",
    "test_32_05_presence_penalty": "采样与输出预算",
    "test_32_06_max_tokens": "采样与输出预算",
    "test_32_09_temperature": "采样与输出预算",
    "test_32_10_stop": "采样与输出预算",
    # #5 流式状态机与完整性
    "test_32_08_stream": "流式状态机与完整性",
    "test_32_12_stream_options": "流式状态机与完整性",
    # #6 结构化输出
    "test_31_07_structured_output": "结构化输出",
    "test_32_11_json_object": "结构化输出",
    # #7 工具调用与多步闭环
    "test_31_08_function_calling": "工具调用与多步闭环",
    # #8 错误码与异常响应
    "test_32_14_auth_security": "错误码与异常响应",
    # #9 参数及输入边界
    "test_31_04_whitelist": "参数及输入边界",
    "test_31_05_rate_limit": "参数及输入边界",
    "test_31_09_context_length": "参数及输入边界",
    "test_32_01_messages": "参数及输入边界",
    "test_32_02_messages_elements": "参数及输入边界",
    "test_32_07_input_length": "参数及输入边界",
    "test_32_13_input_length_nonstream": "参数及输入边界",
    "test_32_15_encoding_special_chars": "参数及输入边界",
    "test_32_17_idempotency": "参数及输入边界",
    # #13 输入 Token 专项对齐
    "test_31_11_token_count": "输入 Token 专项对齐",
    # #14 消息历史与思考回填
    "test_31_03_system_prompt": "消息历史与思考回填",
    "test_32_16_system_prompt_behavior": "消息历史与思考回填",
}


def titles_for(suite: str) -> dict[str, str]:
    """模块名→中文标题映射：k31selfcheck1/k3selfcheck 合并为基线 14 分类；
    k31selfcheck2/k31basesuite/k31selfcheck3 保持各模块具体测试点名。

    k01–k14 的名称本身即《Kimi-K3.1-Pro 供应商自测基线标准》功能兼容性要求表测试项。
    """
    if suite in ("k31selfcheck1", "k3selfcheck"):
        return {**MODULE_TITLES, **BASELINE14_TITLES}
    return MODULE_TITLES


# ---------------------------------------------------------------- 参数子组（采样与输出预算分类内）

SUBGROUP_ORDER = [
    "max_tokens（输出预算）",
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "stop（停止控制）",
    "固定采样值",
]

# 模块 → 参数子组（仅"采样与输出预算"分类内的模块）
SUBGROUP_TITLES = {
    "test_31_02_max_tokens": "max_tokens（输出预算）",
    "test_32_06_max_tokens": "max_tokens（输出预算）",
    "test_32_09_temperature": "temperature",
    "test_32_03_top_p": "top_p",
    "test_32_04_frequency_penalty": "frequency_penalty",
    "test_32_05_presence_penalty": "presence_penalty",
    "test_32_10_stop": "stop（停止控制）",
    "test_k04_sampling_budget": "固定采样值",
}

# k04 特例：预算类用例归 max_tokens 子组（该模块同时含固定采样值与预算用例）
_SUBGROUP_CASE_OVERRIDES = {
    "test_k04_chat_max_completion_tokens_budget": "max_tokens（输出预算）",
    "test_k04_responses_max_output_tokens": "max_tokens（输出预算）",
    "test_k04_messages_max_tokens": "max_tokens（输出预算）",
}


def case_subgroup(suite: str, case_id: str) -> str | None:
    """用例所属参数子组（仅"采样与输出预算"分类内返回非 None；k04 预算用例按名细分）。"""
    name = case_id.split("::")[-1].split("[")[0]
    if name in _SUBGROUP_CASE_OVERRIDES:
        return _SUBGROUP_CASE_OVERRIDES[name]
    return SUBGROUP_TITLES.get(suite.rsplit(".", 1)[-1])


def subgroup_tag(subgroup: str) -> str:
    """子组对应的用例标题参数标签，如 max_tokens（输出预算）→ max_tokens。"""
    return subgroup.split("（")[0]


def suite_title(suite: str) -> str:
    """xxx.tests.test_x → 中文标题（未映射回退原名）。"""
    name = suite.rsplit(".", 1)[-1]
    return MODULE_TITLES.get(name, name)
