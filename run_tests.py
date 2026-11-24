#!/usr/bin/env python
"""K3.1 Serving 验收测试主入口。

用法：
    python run_tests.py engineering [pytest 参数...]
    python run_tests.py k31selfcheck1 --base-url ... --api-key ... --model ...
    python run_tests.py k31selfcheck2 --base-url ... --api-key ... --model ...
    python run_tests.py k31basesuite  --base-url ... --api-key ... --model ...
    python run_tests.py k31selfstress1 --base-url ... --api-key ... [--quick]
    python run_tests.py stress --base-url ... --phase full ...

套件布局：
    engineering/                 工程验收（pytest）
    k31test/function-test/       功能测试：k31selfcheck1 / k31selfcheck2 / k31basesuite（公共用例集）
    k31test/stress-test/         性能：k31selfstress1
    stress/                      压力测试（独立运行器）

公共用例机制（k31basesuite）：功能套件 = 有序文件清单（自有模块与公共模块
按原测试点顺序交错），pytest 按命令行顺序执行；共享框架经 -p k31basesuite.plugin
注入（选项/fixtures/单一 Collector/按 KST_ACTIVE_SUITE 写各套件报告）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FT = ROOT / "k31test" / "function-test"   # 功能测试根（无 __init__.py，pytest 将其插入 sys.path）
ST = ROOT / "k31test" / "stress-test"     # 性能测试根

# pytest 目标（目录直跑，不经有序清单）
SUITES = {
    "engineering": ["engineering/tests"],
    "k3selfcheck": ["k3test/function-test/k3selfcheck/tests"],  # K3 自测（自包含框架）
}

# k31basesuite 公共模块（执行顺序 = 对外版 3.1→3.2 原序）
_FUNC_BASE = [
    "k31basesuite/tests/test_31_01_thinking.py",
    "k31basesuite/tests/test_31_02_max_tokens.py",
    "k31basesuite/tests/test_31_06_cache.py",
    "k31basesuite/tests/test_31_07_structured_output.py",
    "k31basesuite/tests/test_31_08_function_calling.py",
    "k31basesuite/tests/test_31_11_token_count.py",
    "k31basesuite/tests/test_32_03_top_p.py",
    "k31basesuite/tests/test_32_04_frequency_penalty.py",
    "k31basesuite/tests/test_32_05_presence_penalty.py",
    "k31basesuite/tests/test_32_06_max_tokens.py",
    "k31basesuite/tests/test_32_07_input_length.py",
    "k31basesuite/tests/test_32_08_stream.py",
    "k31basesuite/tests/test_32_09_temperature.py",
    "k31basesuite/tests/test_32_10_stop.py",
    "k31basesuite/tests/test_32_11_json_object.py",
    "k31basesuite/tests/test_32_12_stream_options.py",
    "k31basesuite/tests/test_32_14_auth_security.py",
]

# k31selfcheck1：自有 k01–k14 保持原序，公共模块插入对应测试点位（chat 公共面补充）
_K1 = [
    "k31selfcheck1/tests/test_k01_protocols.py",
    "k31selfcheck1/tests/test_k02_usage_cache.py",
    "k31basesuite/tests/test_31_06_cache.py",      # k02 位（usage/缓存）
    "k31selfcheck1/tests/test_k03_thinking_effort.py",
    "k31basesuite/tests/test_31_01_thinking.py",       # k03 位（thinking）
    "k31selfcheck1/tests/test_k04_sampling_budget.py",
    "k31basesuite/tests/test_31_02_max_tokens.py",         # k04 位（预算/采样）
    "k31basesuite/tests/test_32_03_top_p.py",
    "k31basesuite/tests/test_32_04_frequency_penalty.py",
    "k31basesuite/tests/test_32_05_presence_penalty.py",
    "k31basesuite/tests/test_32_06_max_tokens.py",
    "k31basesuite/tests/test_32_09_temperature.py",
    "k31selfcheck1/tests/test_k05_stream_fsm.py",
    "k31basesuite/tests/test_32_08_stream.py",             # k05 位（流式）
    "k31basesuite/tests/test_32_12_stream_options.py",
    "k31selfcheck1/tests/test_k06_structured_output.py",
    "k31basesuite/tests/test_31_07_structured_output.py",      # k06 位（结构化输出）
    "k31basesuite/tests/test_32_11_json_object.py",
    "k31selfcheck1/tests/test_k07_tool_call_loop.py",
    "k31basesuite/tests/test_31_08_function_calling.py",   # k07 位（工具调用）
    "k31selfcheck1/tests/test_k08_error_codes.py",
    "k31basesuite/tests/test_32_14_auth_security.py",          # k08 位（错误/鉴权）
    "k31selfcheck1/tests/test_k09_input_boundaries.py",
    "k31basesuite/tests/test_32_07_input_length.py",            # k09 位（输入边界）
    "k31basesuite/tests/test_32_10_stop.py",
    "k31selfcheck1/tests/test_k10_observability.py",
    "k31selfcheck1/tests/test_k11_timeout_longtask.py",
    "k31selfcheck1/tests/test_k12_multimodal.py",
    "k31selfcheck1/tests/test_k13_input_tokens.py",
    "k31basesuite/tests/test_31_11_token_count.py",           # k13 位（token 对齐）
    "k31selfcheck1/tests/test_k14_history_reasoning.py",
]

# k31selfcheck2：原 29 模块原序，17 个公共模块由 k31basesuite 提供（路径原位替换）
_K2 = [
    "k31basesuite/tests/test_31_01_thinking.py",
    "k31basesuite/tests/test_31_02_max_tokens.py",
    "k31selfcheck2/tests/test_31_03_system_prompt.py",
    "k31selfcheck2/tests/test_31_04_whitelist.py",
    "k31selfcheck2/tests/test_31_05_rate_limit.py",
    "k31basesuite/tests/test_31_06_cache.py",
    "k31basesuite/tests/test_31_07_structured_output.py",
    "k31basesuite/tests/test_31_08_function_calling.py",
    "k31selfcheck2/tests/test_31_09_context_length.py",
    "k31selfcheck2/tests/test_31_10_special_features.py",
    "k31basesuite/tests/test_31_11_token_count.py",
    "k31selfcheck2/tests/test_32_01_messages.py",
    "k31selfcheck2/tests/test_32_02_messages_elements.py",
    "k31basesuite/tests/test_32_03_top_p.py",
    "k31basesuite/tests/test_32_04_frequency_penalty.py",
    "k31basesuite/tests/test_32_05_presence_penalty.py",
    "k31basesuite/tests/test_32_06_max_tokens.py",
    "k31basesuite/tests/test_32_07_input_length.py",
    "k31basesuite/tests/test_32_08_stream.py",
    "k31basesuite/tests/test_32_09_temperature.py",
    "k31basesuite/tests/test_32_10_stop.py",
    "k31basesuite/tests/test_32_11_json_object.py",
    "k31basesuite/tests/test_32_12_stream_options.py",
    "k31selfcheck2/tests/test_32_13_input_length_nonstream.py",
    "k31basesuite/tests/test_32_14_auth_security.py",
    "k31selfcheck2/tests/test_32_15_encoding_special_chars.py",
    "k31selfcheck2/tests/test_32_16_system_prompt_behavior.py",
    "k31selfcheck2/tests/test_32_17_idempotency.py",
]

# k31selfcheck3：功能与兼容性测试清单（指令遵循→stop/结束→tool choice→孤儿tool→
# 一致性→知识库→超时异常→安全围栏，其余公共基础项殿后）
_K3 = [
    "k31selfcheck3/tests/test_33_01_instruction_following.py",          # 1 指令遵循
    "k31basesuite/tests/test_32_10_stop.py",               # 2 stop/结束事件
    "k31basesuite/tests/test_32_08_stream.py",
    "k31basesuite/tests/test_32_12_stream_options.py",
    "k31basesuite/tests/test_31_08_function_calling.py",   # 3 tool choice
    "k31selfcheck3/tests/test_33_02_orphan_tool_message.py",       # 4 孤儿 tool 消息
    "k31selfcheck3/tests/test_33_03_response_consistency.py",         # 5 响应一致性
    "k31selfcheck3/tests/test_33_04_knowledge_probe.py",         # 6 知识库探测
    "k31basesuite/tests/test_32_14_auth_security.py",          # 7 超时与异常
    "k31selfcheck3/tests/test_33_06_timeout_exception.py",
    "k31selfcheck3/tests/test_33_05_safety_guardrail.py",           # 8 安全围栏
    # 其余公共基础项
    "k31basesuite/tests/test_31_01_thinking.py",
    "k31basesuite/tests/test_31_02_max_tokens.py",
    "k31basesuite/tests/test_31_06_cache.py",
    "k31basesuite/tests/test_31_07_structured_output.py",
    "k31basesuite/tests/test_31_11_token_count.py",
    "k31basesuite/tests/test_32_03_top_p.py",
    "k31basesuite/tests/test_32_04_frequency_penalty.py",
    "k31basesuite/tests/test_32_05_presence_penalty.py",
    "k31basesuite/tests/test_32_06_max_tokens.py",
    "k31basesuite/tests/test_32_07_input_length.py",
    "k31basesuite/tests/test_32_09_temperature.py",
    "k31basesuite/tests/test_32_11_json_object.py",
]

# 功能套件（pytest，共享 k31basesuite.plugin 框架）：suite -> 有序文件清单
FUNC_SUITES = {
    "k31selfcheck1": _K1,
    "k31selfcheck2": _K2,
    "k31selfcheck3": _K3,
    "k31basesuite": _FUNC_BASE,
}

# 独立运行器套件（非 pytest）：suite 名 -> (模块, main 函数名, 包父目录)
CUSTOM_SUITES = {
    "stress": ("stress.run_stress", "main", ROOT),
    "k31selfstress1": ("k31selfstress1.run_perf", "main", ST),
}


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("可用套件：")
        for name in list(SUITES) + list(FUNC_SUITES):
            print(f"  {name:<15} (pytest)")
        for name in CUSTOM_SUITES:
            print(f"  {name:<15} (独立运行器)")
        return 0

    suite, rest = args[0], args[1:]

    if suite in CUSTOM_SUITES:
        import importlib
        module_name, main_fn, pkg_parent = CUSTOM_SUITES[suite]
        sys.path.insert(0, str(pkg_parent))
        module = importlib.import_module(module_name)
        print(f"[run_tests] suite={suite} (custom runner)")
        return getattr(module, main_fn)(rest)

    try:
        import pytest
    except ImportError:
        print("错误：未安装 pytest。请先执行：pip install -r requirements.txt")
        return 2

    if suite in SUITES:
        targets = [str(ROOT / p) for p in SUITES[suite]]
        pytest_args = [*targets, "-v", "--tb=short", *rest]
    elif suite in FUNC_SUITES:
        os.environ["KST_ACTIVE_SUITE"] = suite
        sys.path.insert(0, str(FT))  # 使 k31basesuite.plugin 及各功能包可导入
        targets = [str(FT / p) for p in FUNC_SUITES[suite]]
        pytest_args = [*targets, "-v", "--tb=short", "-p", "k31basesuite.plugin", *rest]
    else:
        print(f"错误：未知套件 '{suite}'。可用："
              f"{', '.join(list(SUITES) + list(FUNC_SUITES) + list(CUSTOM_SUITES))}")
        return 2

    print(f"[run_tests] suite={suite}\n[run_tests] pytest {' '.join(pytest_args)}\n")
    return pytest.main(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
