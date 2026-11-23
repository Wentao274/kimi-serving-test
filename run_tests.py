#!/usr/bin/env python
"""K3.1 Serving 验收测试主入口。

用法：
    python run_tests.py engineering [pytest 参数...]
    python run_tests.py engineering --base-url https://vendor.example.com/v1 \
        --api-key sk-xxx --model kimi-k3.1

    python run_tests.py stress --base-url ... --api-key ... --model ... \
        --phase full --agreed-concurrency 50 --agreed-tpm 100000000
    （压力测试：P0 基线→P1 爬坡→P2 平台→P3 脉冲；详见 stress/run_stress.py --help）

后续扩展：
    python run_tests.py kvv      ...（KVV 精度测试，待实现）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 测试套件注册表：suite 名 -> pytest 目标路径
SUITES = {
    "engineering": "engineering/tests",
    "k31selfcheck1": "k31selfcheck1/tests",  # K3.1-Pro 供应商自测基线（功能兼容性）
    "k31selfcheck2": "k31selfcheck2/tests",  # 模型接入要求（对外版）功能测试 3.1/3.2
    # "kvv": "kvv/tests",            # 待实现（或对接官方 Kimi-Vendor-Verifier）
}

# 独立运行器套件（非 pytest）：suite 名 -> (模块, main 函数名)
CUSTOM_SUITES = {
    "stress": ("stress.run_stress", "main"),
}


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("可用套件：")
        for name, path in SUITES.items():
            print(f"  {name:<12} -> {path} (pytest)")
        for name, (mod, _) in CUSTOM_SUITES.items():
            print(f"  {name:<12} -> {mod} (独立运行器)")
        return 0

    suite, rest = args[0], args[1:]
    if suite in CUSTOM_SUITES:
        import importlib
        module = importlib.import_module(CUSTOM_SUITES[suite][0])
        print(f"[run_tests] suite={suite} (custom runner)")
        return module.main(rest)
    if suite not in SUITES:
        print(f"错误：未知套件 '{suite}'。可用：{', '.join(list(SUITES) + list(CUSTOM_SUITES))}")
        return 2

    try:
        import pytest
    except ImportError:
        print("错误：未安装 pytest。请先执行：pip install -r requirements.txt")
        return 2

    target = str(ROOT / SUITES[suite])
    pytest_args = [target, "-v", "--tb=short", *rest]
    print(f"[run_tests] suite={suite}\n[run_tests] pytest {' '.join(pytest_args)}\n")
    return pytest.main(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
