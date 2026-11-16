"""测试配置：从 pytest CLI 选项与环境变量解析。

优先级：pytest CLI 选项 > 环境变量 > 默认值。
环境变量（KST = Kimi Serving Test）：
  KST_BASE_URL / KST_API_KEY / KST_MODEL
  KST_OFFICIAL_BASE_URL / KST_OFFICIAL_API_KEY / KST_OFFICIAL_MODEL（可选，用于 E6 官方基线对照）
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    base_url: str
    api_key: str
    model: str
    official_base_url: str | None = None
    official_api_key: str | None = None
    official_model: str | None = None
    timeout: float = 600.0          # 单请求读超时（秒）
    include_heavy: bool = False     # 是否运行重负载用例（#4 全量 131072 生成等）
    report_dir: str = "reports"

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"

    @property
    def has_official(self) -> bool:
        return bool(self.official_base_url and self.official_api_key and self.official_model)

    def validate(self) -> list[str]:
        problems = []
        if not self.base_url:
            problems.append("缺少 base_url：请通过 --base-url 或环境变量 KST_BASE_URL 提供")
        if not self.api_key:
            problems.append("缺少 api_key：请通过 --api-key 或环境变量 KST_API_KEY 提供")
        if not self.model:
            problems.append("缺少 model：请通过 --model 或环境变量 KST_MODEL 提供")
        return problems


def from_pytest_config(config) -> Settings:
    """从 pytest 配置构造 Settings，环境变量作为回退。"""

    def opt(name: str, env: str, default=None):
        val = config.getoption(name)
        if val is not None:
            return val
        return os.environ.get(env, default)

    return Settings(
        base_url=opt("--base-url", "KST_BASE_URL", "") or "",
        api_key=opt("--api-key", "KST_API_KEY", "") or "",
        model=opt("--model", "KST_MODEL", "") or "",
        official_base_url=opt("--official-base-url", "KST_OFFICIAL_BASE_URL"),
        official_api_key=opt("--official-api-key", "KST_OFFICIAL_API_KEY"),
        official_model=opt("--official-model", "KST_OFFICIAL_MODEL"),
        timeout=float(opt("--timeout", "KST_TIMEOUT", 600.0) or 600.0),
        include_heavy=bool(config.getoption("--include-heavy")),
        report_dir=opt("--report-dir", "KST_REPORT_DIR", "reports") or "reports",
    )
