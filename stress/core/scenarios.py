"""流量模型：四类会话场景、五档长度分布、cache 命中控制、canary 串台标记。

设计依据（serving_requirements.md S3.2/S3.3）：
- 会话混合：text chat / image chat / text claw / image claw；
- 长度覆盖 5 个 TTFT 档位；
- 共享前缀池构造可预测 cache 命中；随机 nonce 前缀探针保证纯 uncached 测量；
- 每个会话植入唯一 canary（UUID 主题）用于串台检测。
"""

from __future__ import annotations

import random
import uuid

from .contract import TIER_NAMES

# 档位目标 prompt tokens（真实执行用；受 --prompt-scale 缩放）
TIER_TARGET_TOKENS = {
    "<8k": 2_000,
    "8k-32k": 16_000,
    "32k-128k": 48_000,
    "128k-256k": 160_000,
    "256k-1m": 300_000,
}

_CHARS_PER_TOKEN = 1.5   # 中英混合语料的经验估算；实际以响应 usage 分档

_BASE_CORPUS_ZH = (
    "在云计算与大模型服务化的大背景下，服务稳定性、延迟分布与吞吐容量是评估一个推理服务平台"
    "是否具备生产可用性的核心指标。一次完整的压力测试需要覆盖从短问答到超长上下文 Agent 会话"
    "的各种形态，并在高并发条件下持续观测首 token 延迟、输出速率与错误率的变化趋势。"
)
_BASE_CORPUS_EN = (
    "Load testing an LLM serving endpoint requires careful control of prompt length "
    "distributions, prefix cache behavior, and output token rates across sessions. "
    "Uncached probe traffic with randomized prefixes is essential to measure true TTFT tiers. "
)

_CLAW_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command and return its output.",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            },
        },
    },
]


def _weighted_choice(rng: random.Random, weights: dict) -> str:
    items = list(weights.items())
    total = sum(w for _, w in items)
    pick = rng.uniform(0, total)
    upto = 0.0
    for key, w in items:
        upto += w
        if pick <= upto:
            return key
    return items[-1][0]


class TrafficBuilder:
    """按配置构造压测请求。"""

    def __init__(self, model: str, scenario_mix: dict, tier_mix: dict,
                 prompt_scale: float = 1.0, shared_prefix_pool: int = 20,
                 image_urls: list[str] | None = None, seed: int = 42):
        self.model = model
        self.scenario_mix = scenario_mix
        self.tier_mix = tier_mix
        self.prompt_scale = max(prompt_scale, 1e-6)
        self.image_urls = image_urls or []
        self.rng = random.Random(seed)
        # 共享前缀池：压测全程固定，用于构造可预测的 prefix cache 命中
        self._prefix_pool = [
            f"[shared-system-prompt-{i:03d}] " + (_BASE_CORPUS_ZH * 3)
            for i in range(shared_prefix_pool)
        ]

    # ------------------------------------------------------------- prompt 构造
    def _corpus_to_tokens(self, target_tokens: int) -> str:
        target_chars = max(int(target_tokens * _CHARS_PER_TOKEN), 16)
        corpus = (_BASE_CORPUS_ZH + _BASE_CORPUS_EN)
        repeats = target_chars // len(corpus) + 1
        return (corpus * repeats)[:target_chars]

    def _prefix(self, cacheable: bool) -> str:
        if cacheable and self._prefix_pool:
            return self.rng.choice(self._prefix_pool)
        return f"[nonce-{uuid.uuid4().hex}] "    # 探针：纯 uncached

    def _text_prompt(self, tier: str, cacheable: bool) -> str:
        target = int(TIER_TARGET_TOKENS[tier] * self.prompt_scale)
        return self._prefix(cacheable) + self._corpus_to_tokens(target) + \
            "\n请概述上述内容的三点要点。"

    # ------------------------------------------------------------- 场景构造
    def build(self, scenario: str, tier: str, canary: str, cacheable: bool) -> dict:
        prompt = self._text_prompt(tier, cacheable)
        prompt_with_canary = f"{prompt}\n（会话标记：{canary}，无需理会）"

        if scenario == "text_chat":
            messages = [{"role": "user", "content": prompt_with_canary}]
            req = {"model": self.model, "messages": messages, "max_tokens": 512}
        elif scenario == "image_chat":
            url = self.rng.choice(self.image_urls) if self.image_urls else \
                "https://example.com/placeholder.png"
            messages = [{"role": "user", "content": [
                {"type": "text", "text": "请描述这些图片。" + prompt_with_canary[:200]},
                {"type": "image_url", "image_url": {"url": url}},
            ]}]
            req = {"model": self.model, "messages": messages, "max_tokens": 512}
        elif scenario in ("text_claw", "image_claw"):
            content: list | str
            if scenario == "image_claw" and self.image_urls:
                content = [
                    {"type": "text", "text": prompt_with_canary[:200] + "\n请先读取配置文件。"},
                    {"type": "image_url", "image_url": {"url": self.rng.choice(self.image_urls)}},
                ]
            else:
                content = prompt_with_canary[:500] + "\n请先读取配置文件 config.yaml。"
            messages = [
                {"role": "system", "content": "You are an agent with tool access."},
                {"role": "user", "content": content},
            ]
            req = {"model": self.model, "messages": messages,
                   "tools": _CLAW_TOOLS, "tool_choice": "auto", "max_tokens": 512}
        else:
            raise ValueError(f"未知场景: {scenario}")

        req["thinking"] = {"type": "enabled"}
        return req

    def pick(self) -> tuple[str, str, bool]:
        """返回 (scenario, tier, cacheable)。"""
        scenario = _weighted_choice(self.rng, self.scenario_mix)
        tier = _weighted_choice(self.rng, self.tier_mix)
        cacheable = self.rng.random() < 0.7     # 70% 走共享前缀池，30% 纯 uncached 探针
        return scenario, tier, cacheable

    def probe(self, tier: str, canary: str) -> dict:
        """基线校准探针：纯 uncached，用于真实档位 TTFT 测量。"""
        return self.build("text_chat", tier, canary, cacheable=False)


def default_image_urls() -> list[str]:
    """缺省图片源：从工程验收图片用例中提取少量 URL（有效期至 2027-03-18）。"""
    try:
        from engineering.core.data import load_image_cases
        urls: list[str] = []
        for row in load_image_cases():
            for m in row.get("transformed_request", {}).get("messages", []):
                content = m.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        iu = part.get("image_url")
                        url = iu.get("url") if isinstance(iu, dict) else iu
                        if isinstance(url, str) and url.startswith("http") and url not in urls:
                            urls.append(url)
                if len(urls) >= 5:
                    return urls
        return urls
    except Exception:
        return []
