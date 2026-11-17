# K3.1 流量外采要求 — 分析归纳与测试实现方案

> 源文档：《K3.1 流量外采要求 / K3.1 Serving Requirements》（飞书 wiki，导出 Markdown）
> 附件：`vendor-img-testcases-inhouse-3.jsonl`（25 条图片用例）、`9.openclaw_cases12.jsonl`（12 条 OpenClaw 用例）
> 本文档：对源文档的完整分析归纳 + 工程验收 / 精度验收 / 压力测试的详细实现方案。

---

## 第一部分：要求文档全面分析归纳

### 1. 文档结构总览

源文档由三大部分组成：

| 部分 | 内容 | 性质 |
|---|---|---|
| 合同要求 (Contract Requirements) | 7 条：精度一致性、TTFT、OTPS、Cache 命中率、429 约定、SLA、RTO | 服务期持续约束，违约有责 |
| 上线前条件 (Pre-Launch Requirements) | 9 条：KVV 精度自测、thinking mode、参数默认值、max_tokens、System Prompt、图片用例、OpenClaw 用例、Trace/统计、Preserve Thinking | 上线门槛，自测+官方验证 |
| K3.1 Test Results | 工程验收、精度验收（KVV / deepSWE / KCB）、压力测试条款 | 验收执行标准 |

**测试阶段资源基线（Some Tips）**：以 1000 RPM / 25M TPM 起步；精度测试阶段支持 25–30 并发；压力测试阶段支持 50+ 并发、TPM ≥ 100M、持续观测 24 小时。正式合作阶段按约定 RPM/TPM。

### 2. 合同要求 7 条逐项分析

#### 2.1 精度一致性
- 服务期精度须与上线前一致；重大更新必须通知甲方并重测（KVV logprobs）。
- **红线**：私自更新且 KVV 任一测试集结果差异 > 2% → 对应时间段判定为不可用。

#### 2.2 TTFT（Time to First Token）分档要求

| uncached_tokens | P50 | P90 |
|---|---|---|
| <8k | 2 s | 4 s |
| 8k–32k | 4 s | 6 s |
| 32k–128k | 10 s | 20 s |
| 128k–256k | 25 s | 45 s |
| 256k–1m | 35 s | 100 s |

要点：按 **uncached tokens**（非总 prompt tokens）分档，因此 cache 命中直接影响 TTFT 达标档位；需同时考核 P50 与 P90。

#### 2.3 OTPS（Output Tokens Per Second）
- OTPS > 30；统计周期内不达标请求占比 > 1% → 该周期不可用。
- 要点：是**逐请求**指标 + **1% 容错比例**，不是平均值考核。

#### 2.4 Cache 命中率（CacheGT 机制）
- 结算规则：实际命中率 < 理论值按理论值结算（乙方吃亏）；超过理论值按实际结算。
- CacheGT 理论值算法核心：
  - **Block 计算**：tokenizer 将 prompt 转 tokens，按固定大小切连续 blocks，相同前缀 → 相同 block 序列；
  - **2 小时时间窗口**：只有最近 2 小时内记录过的前缀 blocks 参与命中计算；
  - **处理流程**：Prefix Match（从 prompt 开头按 block 顺序匹配连续前缀，首个未命中 block 即停止，累计为 `cached_tokens`）→ Record（记录本请求 block 序列供后续匹配）；
  - 命中率公式：`Cache Hit Rate = Σ cached_tokens_2h / Σ prompt_tokens`。
- 要点：验收时需用官方 CacheGT 口径复算供应商上报的 cached_tokens。

#### 2.5 429 约定
- TPM 超过约定值时应**立即返回 429，而不是排队等待**。即不允许用延迟来吸收超量流量（否则会污染 TTFT 统计）。

#### 2.6 SLA 承诺（月度 ≥ 99%）
- 前提：甲方请求合法规范，且 TPM 不超过"负载阈值"（过去 7 天每分钟峰值的平均值）。
- **不可用判定**（连续 10 分钟窗口，满足其一即计入不可用时间）：
  1. 请求失败率 ≥ 1%；
  2. 精度 / TTFT / OTPS 不满足条款 1/2/3。
- **请求失败定义**：
  - TPM ≤ 负载阈值：返回非 2xx → 失败；
  - TPM > 负载阈值：返回 2xx、429 之外的状态码 → 失败（429 不算失败）。
- 公式：`SLA = (总服务时间 − 不可用时间) / 总服务时间 × 100%`。
- 要点：监控口径必须按 10 分钟滑动窗口聚合；429 行为与 2.5 条联动。

#### 2.7 RTO 承诺
- 高峰期（北京时间 08:00–24:00，含节假日）：RTO ≤ 10 分钟；
- 低峰期（00:00–08:00）：RTO ≤ 60 分钟；
- 跨时段故障按**故障起始时段**标准执行；超时未恢复甲方可主张 SLA 违约赔偿。

### 3. 上线前条件 9 条逐项分析

1. **KVV 精度自测**：与官方结果接近；闭源测试 traj 不得保存、不得内部使用或针对性调优；平台与数据严格使用 KVV（github.com/MoonshotAI/kvv-k3）。
2. **Thinking mode**：必须同时支持 `thinking.type = enabled/disabled`，默认 enabled（disabled 仅作兼容，不推荐）；enabled 下 `thinking effort` 支持 low / high / max 三档，默认 max。
3. **参数默认值与官方一致**：

   | Parameter | Thinking Mode | Disabled Thinking |
   |---|---|---|
   | temperature | 1.0 | 0.6 |
   | top_p | 0.95 | 0.95 |
   | presence_penalty | 0 | 0 |
   | frequency_penalty | 0 | 0 |
   | n | 1 | 1 |

4. **max_tokens** 默认 131072，允许用户修改。
5. **不得默认添加任何 System Prompt**。
6. **图片输入用例**（附件 25 条）：覆盖两种 `image_url` schema（字符串 vs `{"url": ...}` 对象）、两种 finish_reason（stop / tool_calls）、图片位于 `role=user` 与 `role=tool` 消息、最多 1000 张图片（中文段落写"100 张"但英文与实际用例 case25 为 1000 张，**以 1000 为准**）、格式 jpeg/png/gif/tiff/bmp/webp/heic。**注意：http 图片 URL 2027-03-18 失效**。
7. **OpenClaw tool call 用例**（附件 12 条）：OpenClaw 是 tool call 的高频特例，全部用例期望 `finish_reason == "tool_calls"`。
8. **其他基础要求**：支持 Trace ID（OpenTelemetry）；Token 统计支持按 model_id、text chat、image chat、text claw、image claw 分类。
9. **Preserve Thinking**：`thinking: {type: enabled, keep: all}` 时，须保留并回传历史 reasoning_content 参与上下文。验证锚点：指定请求 prompt tokens = 160，响应含与请求中完全一致的 5 个数字（473, 921, 235, 215, 222）。

### 4. 附件测试用例集分析（实测解析结论）

#### 4.1 `vendor-img-testcases-inhouse-3.jsonl`（25 条）
- 行结构：`{"expected_finish_reason": "stop"|"tool_calls", "transformed_request": {...标准 chat.completions 请求...}}`；model 字段为占位符 `dummy-vendor-model`，执行时替换为供应商模型名。
- 分布：19 条期望 `stop`，6 条期望 `tool_calls`；图片共 1224 张。
- 覆盖矩阵（实测）：
  - schema：case12 混用 str+dict，case22 纯 str，其余 dict；
  - 图片位置：case5/12/19/20/22/23/24 图片在 `role=tool` 消息中，其余在 `role=user`；
  - 量级：case25 单请求 1000 张图（上限压力），case15/17 约 46–48 张，case3 43 张；
  - thinking：多数 `disabled`，case23/24 未传 thinking 字段（走默认 enabled）；
  - 特殊：case23/24 为视频分析场景（`watch_video_screenshot` 工具，历史中含 reasoning_content + tool_calls）。
- 图片源为 `https://blobproxy.moonshot.cn/...` 签名 URL（2027-03-18 过期）。

#### 4.2 `9.openclaw_cases12.jsonl`（12 条）
- 行结构：`{"line": N, "request": {...}}`；model=`kimi-k2.5`（执行时按需替换）。
- 特征：真实 OpenClaw 多轮 agent 轨迹，16–364 条消息、54–408 KB/条；工具数 1–61 个。
- 多数 case：`thinking.enabled` + temperature=1 + top_p=0.95 + max_tokens=32768 + `stream=true` + `stream_options={include_usage, include_internal_content}`；历史 assistant 消息携带 `reasoning_content`（考验 preserve thinking 与长上下文）。
- 特例：case11 为单 user 消息 + `tool_choice=auto`（最小触发）；case12 为 `thinking.disabled` + temperature=0.6 + `max_completion_tokens=16384` + `stream=false`（非流式 + max_completion_tokens 兼容性）。
- 全部期望以 `finish_reason == "tool_calls"` 结束。

### 5. 关键差异 / 风险点提示

1. **图片数量中英文不一致**：中文"支持最多 100 张" vs 英文"Supports 1000 images"，实测 case25=1000 张 → 按 1000 验收。
2. **闭源数据合规**：KCB、压力测试为闭源测试，受测方不得保存任何测试数据；KVV traj 不得保存/调优。测试侧（甲方）也需隔离存储与访问审计。
3. **图片 URL 时效**：2027-03-18 后失效，自动化用例需在此之前执行或替换图床。
4. **TTFT 分档按 uncached_tokens**：构造 TTFT 测试集时必须控制 cache 命中变量（如随机化 nonce 前缀），才能落入目标档位。
5. **429 与 SLA 联动**：压测超阈值时 429 不计失败，但"立即返回"是硬要求，需专门验证。

---

## 第二部分：测试实现方案

总体原则：以供应商提供的 `endpoint + API key` 为唯一入口，全部测试黑盒执行；测试工程建议落在本仓库（kimi-serving-test），技术栈建议 Python 3.11+ / httpx / openai SDK / pytest / locust（压测）/ pandas（统计分析），产出 JUnit XML + HTML 报告 + 原始指标 CSV。

### 一、工程验收项（Interface / Functional Acceptance）实现方案

目标：验证供应商接口在协议、参数、功能行为上与官方完全兼容。验收条目**对齐原始需求文档《K3.1 流量外采要求》"K3.1 Test results → 一、工程验收 / Interface Results"表格**（该表格在 markdown/PDF 导出中内容缺失，已按文档截图 OCR 还原；个别 OCR 噪声处以英文原文为准）。工程验收通过自研脚本实现，测试工程见 `engineering/` 目录。

| # | 工程验收条目（截图表格） | 要求内容 | 实现方法 | 通过标准 |
|---|---|---|---|---|
| #1 | Thinking Mode Activation | thinking 字段使用 anthropic style，在 request body 中加上 `{"thinking": {"type": "enabled"}}`；默认开 thinking；同时支持 enabled/disabled（disabled 仅兼容，不推荐） | `test_01_thinking_mode.py`：enabled/disabled/不传 thinking 各发请求（含流式与非流式），校验响应结构 | enabled 必含 reasoning_content；disabled 必不含；不传默认 = enabled；结构正确 |
| #2 | 参数默认值 | 默认值和官方保持一致（thinking：temperature=1.0/top_p=0.95/presence_penalty=0/frequency_penalty=0/n=1；disabled：temperature=0.6）；**temperature 默认 1.0，修改为其他值需返回 HTTP 400**（An error must be returned if the value is out of range） | `test_02_param_defaults.py`：不传采样参数请求成功；显式默认值被接受；无参 vs 显式默认的 logprobs 分布指纹一致；**非官方默认值必须返回 HTTP 4xx（硬校验）** | 默认值表全部被接受；无参 ≡ 显式默认（token 序列一致；端点不支持 logprobs 时跳过并记录）；非默认值全部 4xx |
| #3 | max_tokens | 默认值为 131072，允许用户修改 | `test_03_max_tokens_default.py`：显式传 131072 被接受；显式传小值生效；不传时可生成 >4096 tokens（代理验证）；完整 131072 上限验证为 heavy 用例（`--include-heavy`，约 70+ 分钟） | 显式 131072 接受；显式小值生效；默认值非小值；heavy 下生成至 finish=length 且 completion_tokens ≥ 131072 |
| #4 | System Prompt | 供应商默认不添加任何 System Prompt | `test_04_no_system_prompt.py`：身份探针（硬校验，应回答 Kimi/Moonshot 原生身份）；提示词泄露探针（记录人工复核）；可选 `--official-*` 官方基线对照（soft） | 身份探针体现原生身份；无证据表明注入额外 system prompt（泄露探针与对照结果供人工复核） |
| #5 | image 输入测试用例 | 跑通附件 25 条用例，覆盖：两种 `image_url` 格式（字符串 vs `{"url": ...}`）、两种 finish_reason（stop/tool_call）、图片位于 role=user / role=tool 消息、最多 1000 张图片、jpeg/png/gif/tiff/bmp/webp/heic 七种格式；用例有效期至 2027-03-18（表格备注：可用 prompt tokens case 来验证） | `test_05_image_cases.py`：回放 `vendor-img-testcases-inhouse-3.jsonl`，逐行取 `transformed_request` 替换 model；每条按原生 stream 跑一遍 + 翻转 stream 再跑一遍（case25 千图 flipped 需 `--include-heavy`）；**格式维度**由 `test_05_image_formats` 以本地生成的 7 种格式 base64 小图（免图床）逐格式验证供应商解码能力（附件图片均来自 blobproxy 无格式标记，不覆盖格式维度） | 25/25 `finish_reason == expected_finish_reason`；两种 schema、user/tool 位置、1000 图全部跑通；7 种格式均 2xx 且响应正常；无 5xx/超时 |
| #6 | Trace ID | 支持 trace ID（OpenTelemetry）（用途：E2E debug） | `test_06_trace_id.py`：携带 W3C traceparent 头发送请求必须正常受理（2xx）；检查响应头/响应体中是否返回 trace 标识（x-trace-id/traceparent/x-request-id 等，soft，回传方式文档未约定，需人工结合供应商网关确认） | 携带 traceparent 的请求 2xx；trace 标识回传情况记录待人工确认 |
| #7 | Token 统计分类 | 工程验收表：Token statistics must support categorization by model_id；上线前条件 #8.b 完整版：categorization by **model_id, text chat, image chat, text claw, image claw**（用途：月度/季度对账） | **暂不实现**（功能性验收，无附件用例文件）：阻塞依赖为供应商 token 统计/对账查询接口的方式与文档；拟定思路——复用 stress 场景构造发送已知量的 text chat / image chat / text claw / image claw 四类流量，查询统计接口核对五维度分类准确且互不串计；`test_07_token_statistics.py` 占位，报告中以 SKIPPED+原因 标注 | 统计接口可查、五维度分类、数值与已知流量一致 |
| #8 | X-Msh-ProviderDeployId | 在 response header 中支持 `"X-Msh-ProviderDeployId": <deployment id>` 字段，breaking change 后版本变更可见 | `test_08_provider_deploy_id.py`：非流式与流式请求的响应头中均应包含该字段且值非空（硬校验） | 两种模式响应头均含非空 X-Msh-ProviderDeployId |
| #9 | Streaming Output Spec | 支持《Streaming Output Spec List for Vendor (EN)》中的 P0 和 P1 要求，并通过测试 | **暂不实现**：需获取《Streaming Output Spec List for Vendor (EN)》规范文档；`test_09_streaming_output_spec.py` 占位，报告中以 SKIPPED+原因 标注 | （待规范文档到位后定义） |
| #10 | New Model Spec（K3.1 新功能） | 支持《New Model Spec List for Vendor》中的功能并通过测试（K3.1 涉及的新功能） | **暂不实现**：需获取《New Model Spec List for Vendor》规范文档；`test_10_new_model_spec.py` 占位，报告中以 SKIPPED+原因 标注；preserve thinking 预计归属该范围（见下方说明） | （待规范文档到位后定义） |

**补充条目（"上线前条件"中有明确要求、工程验收截图表格中未单列，脚本已覆盖）：**

| 原始条目 | 要求内容 | 实现方法 | 通过标准 |
|---|---|---|---|
| 上线前#2（effort 部分） | thinking mode 下 effort 支持 low/high/max 三档，默认 max | `test_11_thinking_effort.py`：三档可接受性；询问模型生效档位硬校验；reasoning 长度排序 soft 记录 | 三档均被接受且含 reasoning_content；模型报告档位与所设一致；不传 effort 时模型报告 = max |
| 上线前#7 | Tool call（OpenClaw）测试用例：供应商应能处理 tool call 测试用例，全部请求应返回 `finish_reason='tool_calls'` | `test_12_openclaw_cases.py`：回放 `9.openclaw_cases12.jsonl`，取 `request` 字段原样发送（含 stream/thinking/max_completion_tokens 等配置），大 prompt case 超时翻倍 | 12/12 以 `finish_reason == "tool_calls"` 结束；tool_calls 结构合法（name 非空、arguments 为合法 JSON）；长上下文 case（300KB+）不截断、不报错 |
| 上线前#9 | Preserve thinking：`thinking:{type:enabled, keep:all}` 时保留全部历史思考；验证锚点：指定请求 prompt tokens=160，响应含与请求完全一致的 5 个数字 | `test_13_preserve_thinking.py`（自研，已实现）：发送需求文档给定的锚点请求，硬校验 usage.prompt_tokens==160（历史 reasoning_content 被保留）+ 响应含全部 5 个数字且一致；不传 keep 的对照为 soft（观察默认丢弃/保留口径）。KVV 侧仍无 preserve-thinking 用例（见下方说明），本实现与其后续补充互补 | prompt_tokens=160；5 数字完全一致 |

**Preserve thinking / KVV 覆盖情况调研结论（基于 Kimi-Vendor-Verifier 仓库实际核查）：**

- KVV 的 `tests/prompt_tokens/` 套件与 preserve thinking 的验证思路相同（校验 `usage.prompt_tokens` 与 groundtruth 常量一致），其用例集 `testdata/prompt_token_cases/cases.jsonl` 的 k3 系列迁移自 serve/tokenism 仓库；
- 但 KVV 用例集 README **明确声明 "Interleaved / preserved-thinking cases (CT-004, CT-013, CT-014, CT-015, CT-017, CT-018) are not migrated"**（交错/保留思考用例未迁移，两处声明）——即 **当前 KVV 尚未包含 preserve thinking（K3.1 保留历史思考新功能）的测试用例**；
- KVV 已在其他方面支持 K3.1：README 含 K3.1 Pro 各供应商验证结果表（OCRBench / MMMU Pro Vision / BEAM 1M / DeepSWE / ToolCall bench）；`tests/k3_features/` 覆盖 thinking effort 等 K3 特性（请求中会携带 `thinking:{type, keep:all, effort}`，但不校验历史思考保留行为）；
- 结论：preserve thinking 可借助 KVV 的 prompt_tokens 测试框架执行，但**需要 Kimi 团队补充 preserve-thinking 专用用例（含 expected_prompt_tokens 常量与内容断言）**；该功能预计归属工程验收表 #10《New Model Spec List for Vendor》范围，执行前需与 Kimi 团队确认用例与规范文档（contact-kvv@kimi.com）。

执行与产出：`python run_tests.py engineering --base-url ... --api-key ... --model ...`；每用例的请求/响应/断言/curl 复现命令自动落盘，输出单文件 HTML 报告 + 全量 JSON 数据至 `reports/engineering_<时间戳>/`（闭源用例数据按合规要求处理后即焚）。

前置说明：`test_00_smoke_connectivity.py` 为前置冒烟检查（/models、最小 chat、错误 key、未知模型、128 字符工具名），用于测试前的基础设施 sanity check，**不属于验收条目**。

### 二、精度验收项（Accuracy Acceptance）实现方案

目标：证明供应商 serving 的 K3.1 精度与官方一致。三个子项，并发控制在 25–30。

#### A2.1 KVV 精度验证（核心，对应合同条款 1）
1. 环境：按官方仓库 `github.com/MoonshotAI/kvv-k3` 搭建，数据与平台严格使用 KVV 附件指定版本。
2. 执行：对供应商 endpoint 跑全部 KVV 测试集，采集 logprobs；相同测试集对官方 endpoint（或官方公布基线）跑对照。
3. 判定：**任一测试集结果差异 > 2% 即不通过**（与服务期"私自更新"同一判定口径，验收阈值对齐合同）。
4. 合规：traj 不保存、不用于调优；跑完即按约定销毁，保留聚合分数与审计日志。
5. 基线参照：文档"K3.1 Test Results → 2.1 Think Mode"指向 kvv-k3 仓库中的官方结果。

#### A2.2 deepSWE（Agent benchmark，公开）
1. 平台：开源 pier 平台；用例集 `github.com/datacurve-ai/deep-swe`（113 题）；配置参照 `github.com/MoonshotAI/Kimi-Vendor-Verifier`。
2. 关键配置：kimi-code **0.40.1**、effort=max、config.toml、`agent-timeout-multiplier=50`、`max-step=20000`。
3. 判定基准（官方结果）：**score 75.5 avg@3**，平均 output tokens **102~103k**。验收跑 avg@3，score 与官方偏差需在约定容差内（建议 ≤2% 与 KVV 口径一致），并核对平均 output tokens 量级作为行为一致性旁证。

#### A2.3 Kimi Code Bench（KCB，闭源）
1. 方式：endpoint 准备好后**移交 Kimi 团队执行**，受测方不参与、不保存数据。
2. 官方基准：**score 75.0 avg@5**，平均 output tokens **39.2K**。
3. 测试侧仅需：提供可用 endpoint/key、约定测试窗口、保障期间容量（25–30 并发）。

产出：精度验收报告（KVV 各测试集对比表、deepSWE avg@3 分数与 token 统计、KCB 移交记录），差异分析（如有）。

### 三、压力测试（Stress Test）分析与设计方案（已实现，见 S3.4）

> 依据：PDF 全文（Some Tips、合同要求 7 条、三、压力测试条款）。压力测试由 **Moonshot 执行**、闭源（受测方不得保存任何测试数据）；供应商保障资源。

#### S3.1 需求与指标提取（PDF 全量结构化）

**A. 容量指标**

| 指标 | 取值 | 出处 |
|---|---|---|
| 起步负载 | 1000 RPM / 25M TPM | Some Tips |
| 压测并发 | ≥ 50 并发（测试期）；正式阶段 ≥ 约定并发量 | Some Tips / 压力测试条款 |
| 总 TPM | 测试期 ≥ 100M；正式 ≥ 约定量 | Some Tips / 压力测试条款 |
| **uncached ITPM** | ≥ 约定量（非缓存输入吞吐单独考核） | 压力测试条款 |
| 持续时间 | 连续 24 小时压测 + 持续观测 | Some Tips / 压力测试条款 |

**B. 性能指标（合同第 2/3 条，压测通过标准直接引用）**

| uncached_tokens | TTFT P50 | TTFT P90 |
|---|---|---|
| <8k | 2 s | 4 s |
| 8k–32k | 4 s | 6 s |
| 32k–128k | 10 s | 20 s |
| 128k–256k | 25 s | 45 s |
| 256k–1m | 35 s | 100 s |

- OTPS > 30（逐请求）；统计周期内不达标请求占比 > 1% → 该周期不可用。

**C. 可靠性指标（合同第 5/6 条）**

- 429：TPM 超约定值应**立即返回 429，不得排队等待**；
- 不可用窗口：连续 10 分钟内请求失败率 ≥ 1%，或精度/TTFT/OTPS 不达标 → 计为不可用；
- 失败定义分档：TPM ≤ 负载阈值（过去 7 天每分钟峰值平均）→ 非 2xx 为失败；TPM > 负载阈值 → 2xx/429 之外为失败；
- SLA =（总服务时间 − 不可用时间）/ 总服务时间 × 100%，月度 ≥ 99%。

**D. 质量指标（压测期间）**：无字符重复（character repetition）、无工具调用重复（tool call repetition）、无串台（cross-session leakage）、无无意义输出（nonsensical output）。

**E. 结算相关（合同第 4 条）**：cache 命中率低于 CacheGT 理论值按理论值结算；超过按实际。理论值 = 2h 窗口 prefix cache 命中（Σ cached_tokens_2h / Σ prompt_tokens）。

**F. 合规**：闭源测试，测试数据受测方不得保存；Moonshot 执行，合作方准备充足资源。

#### S3.2 关键分析（口径、难点与指标联动）

1. **TTFT 档位由 uncached_tokens 决定 → 压测流量必须可控 cache 命中**：若流量前缀高度重复，大部分请求命中缓存，uncached_tokens 变小，TTFT 被"美化"，无法验证真实档位（尤其 32k 以上大档）。设计必须包含**前缀可控流量**：共享前缀池（构造可预测的命中）+ 随机 nonce 前缀探针（保证纯 uncached 测量）。
2. **uncached ITPM ≥ 约定量是容量验证的核心难点**：供应商不能靠前缀缓存凑 TPM——压测流量中 uncached 输入 token 速率必须持续 ≥ 约定量，流量设计需按 uncached tokens/min（而非仅 RPM）做速率规划。
3. **OTPS 是逐请求指标 + 1% 容错，不是均值**：需逐请求计算生成速率（completion_tokens / 生成时长），统计分布而非平均；高并发下尾部请求（排队、长输出）最易触碰 1% 红线。
4. **429"立即返回"与 TTFT P90 100s 的张力**：超量时排队即违约。压测需含**超额脉冲**，验证 429 响应时延（秒级而非排队至处理）以及恢复后无积压效应。
5. **SLA 口径 = 10 分钟窗口**：24h 压测 = 144 个窗口，监控聚合必须与合同同口径（窗口内失败率/TTFT/OTPS 三判据），且失败定义随 TPM 相对负载阈值的位置切换——压测前需先**建立负载阈值基线**（或以约定值代入）。
6. **精度在压测中的代理化**：合同把"精度不达标"纳入 10 分钟窗口判据，但压测期间无法逐窗口跑 KVV；工程上以**质量四项（重复/串台/无意义）+ 压测前后各一次 KVV 快检**作为在线精度代理。
7. **24h 覆盖高低峰切换**：可在窗口内顺带执行 RTO 演练（高峰 ≤10min / 低峰 ≤60min，跨时段按起始时段计），一次压测同时产出 SLA 与 RTO 证据。
8. **cache 命中率影响结算**：压测流量前缀模式会被 CacheGT 记录并影响理论值，流量设计需留档前缀计划，便于按 CacheGT 口径复算对账。

#### S3.3 压力测试设计方案

**前置条件**：工程验收、精度验收通过；供应商提供监控数据（或导出日志）；确定约定并发/TPM/uncached ITPM 数值与负载阈值基线；测试窗口约定（含数据合规要求）。

**流量模型设计**：
- 会话混合：text chat / image chat / text claw / image claw 四类（兼顾 token 分类统计与生产特征）；
- 长度分布：覆盖 5 个 TTFT 档位（<8k / 8k–32k / 32k–128k / 128k–256k / 256k–1m 各档占比按生产分布，超长档低保有量以控制成本）；
- cache 命中控制：共享前缀池（模拟系统提示/ few-shot 复用）+ 随机 nonce 探针流（纯 uncached）；两部分流量速率分别规划，确保 uncached ITPM ≥ 约定量；
- 输出长度：短/中/长输出混合（含 max_tokens 大输出，暴露 OTPS 尾部）。

**阶段划分**：

| 阶段 | 内容 | 产出 |
|---|---|---|
| P0 准备 | 基线校准：负载阈值确认、各档位流量小流量冒烟、监控链路打通 | 基线记录 |
| P1 爬坡 | 1000 RPM / 25M TPM 起步，阶梯加至约定并发/TPM（每阶稳定 15–30 min） | 爬坡曲线、拐点识别 |
| P2 峰值平台 | 约定并发（测试期 50+）/ TPM（测试期 ≥100M）持续 **24h**，全程 10min 窗口监控 | 容量稳定性证据、SLA 窗口明细 |
| P3 脉冲 | 叠加瞬时超约定 TPM 脉冲，验证立即 429（时延、不排队）、恢复无积压 | 429 行为报告 |
| P4 故障演练（建议） | 高峰/低峰各注入一次不可用，测 RTO（≤10/≤60 min） | RTO 证据 |
| P5 收尾 | 压测后 KVV 快检（精度代理复核）、数据合规清理、报告 | 验收结论 |

**采集与监控（10 分钟滑动窗口，对齐 SLA 口径）**：
- 逐请求记录：TTFT、总时延、OTPS（completion_tokens/生成时长）、状态码、prompt/cached/completion tokens、会话 ID；
- 聚合：TTFT 按 uncached_tokens 分档 P50/P90；OTPS 不达标占比；失败率（按 TPM 阈值内外口径）；RPM/TPM/uncached ITPM/并发曲线；429 率与 429 响应时延；
- cache：供应商上报 cached_tokens vs CacheGT 理论值复算对比。

**质量检测设计（压测全程）**：
- 字符重复：滑窗 n-gram 重复率检测，超阈值告警 + 人工复核；
- 工具调用重复：同请求内连续相同 (name, arguments) tool_calls 死循环检测；
- 串台：每并发会话植入唯一 canary（随机 UUID 主题），检测 A 会话内容泄露至 B 会话响应；
- 无意义输出：采样 + 轻量判别（规则/困惑度）+ 人工抽检。

**通过判定矩阵（映射压力测试条款）**：

| 条款要求 | 判定口径 |
|---|---|
| 实际容量稳定达到约定上限 | 24h 内 RPM/TPM/并发无塌陷（无 >10min 的持续容量跌落） |
| TTFT 达到约定要求 | 各 uncached 档位 P50/P90 全程达标（按 10min 窗口） |
| OTPS 达到约定要求 | 各窗口不达标请求占比 ≤1% |
| 无字符重复/工具调用重复/串台/无意义输出 | 四项质量检测零确认事故（告警经人工复核均闭环） |
| （联动）SLA | 144 个 10min 窗口无"不可用"计入 |

**数据合规**：闭源测试数据不落地保存于受测侧；监控采集侧仅保留聚合指标与匿名化元数据；原始请求/响应按约定测试后即焚，留档仅为聚合报告。

**开放问题（执行前需与 Kimi 团队确认）**：① 约定并发/TPM/uncached ITPM 的具体数值；② 负载阈值在压测期的代入口径（7 天基线 vs 约定值）；③ 256k–1m 超长档的流量占比与成本预算；④ cache 理论值复算是否由 Kimi 侧 CacheGT 统一执行。

产出：压测报告（容量曲线、TTFT/OTPS 分档窗口统计、SLA 窗口明细、429 与 RTO 演练记录、质量检测结论、问题清单与整改项）。

#### S3.4 实现与使用（已实现，套件 `stress/`）

按上述方案实现为 `stress` 套件（`run_tests.py stress`），结构：

```
stress/
├── run_stress.py            # CLI 入口（run_tests.py 已注册分发）
└── core/
    ├── contract.py          # 客户文档合同阈值唯一出处：TTFT 五档表、OTPS 30/1%、
    │                          10min 窗口、失败率 1%、起步/压测容量基线
    ├── config.py            # CLI/环境变量：约定并发/TPM/uncached ITPM、负载阈值、阶段时长
    ├── async_client.py      # 异步流式客户端：逐请求 TTFT/gen 时长/OTPS/cached_tokens
    ├── scenarios.py         # 流量模型：四类会话、五档长度、共享前缀池+nonce 探针、canary
    ├── quality.py           # 质量四项检测（字符重复/tool call 重复/串台/无意义）
    ├── metrics.py           # 10min 窗口聚合（蓄水池采样）+ 合同口径判定
    ├── generator.py         # 阶段引擎 P0-P3：worker 池伸缩、窗口快照、事故记录
    └── report.py            # 单文件 HTML（判定矩阵/基线/窗口明细/曲线/事故）+ JSON
```

执行（真实 24h 压测）：

```bash
python run_tests.py stress --base-url https://vendor/v1 --api-key sk-xxx --model <模型> \
    --phase full \
    --agreed-concurrency 50 --agreed-tpm 100000000 --agreed-uncached-itpm <约定值> \
    --load-threshold-tpm <7天峰值平均> \
    --platform-duration 86400 --spike-duration 120
```

- **阶段**：`baseline`(P0 各档 uncached 探针) → `ramp`(P1 阶梯，1000RPM/25MTPM 起步可用 `--ramp-stages` 定制) → `platform`(P2 约定并发 24h，结束后自动判定) → `spike`(P3 超量脉冲验证立即 429)；`full` 全流程。
- **产出**：`reports/stress_<时间戳>/` 下 `report.html`（判定矩阵/窗口明细/曲线/质量事故）、`summary.json`、`windows.json`（窗口快照，长跑中断不丢）、`metrics.jsonl`（逐请求指标，**不含原始请求/响应，符合闭源数据合规**）、`quality_incidents.json`。
- **判定口径**：与客户文档逐条对齐——容量无 >10min 塌陷、各 uncached 档 TTFT P50/P90 逐窗口达标、OTPS 窗口超标占比 ≤1%、失败率 <1%（按 TPM 阈值内外切换口径）、脉冲期 429 时延 P90 ≤5s（可调）、质量四项零确认事故。退出码：有判定失败即非 0。
- **RTO 演练（P4）**：故障注入需供应商配合摘流，测试侧无法独立完成——执行时以人工/供应商操作触发，用本套件 `platform` 阶段的窗口失败率曲线观测恢复时长，对照高峰 ≤10min / 低峰 ≤60min 判定（不内置自动化）。
- 设计修正记录（实现中发现并已修复）：① 平台期判定窗口必须按阶段多数归属过滤，否则爬坡/脉冲窗口混入误判；② 未关闭的边界窗口不参与容量判定（速率偏估），但脉冲期 429 判定需用"包含脉冲请求的窗口"（429 时延与窗口完整性无关，否则短脉冲在 600s 窗口中必然漏判）。
- demo 验证：`--window-s 10 --prompt-scale 0.001 --platform-duration 20 --spike-duration 6 --ramp-stages "warm:5:4,climb:5:8"` 可对 mock 全链路验证（本仓库已在本地 mock 上限流下验证通过：平台各项判定通过、脉冲 429 P90=0.735s 判定通过）。

**执行前必须确认的输入**（对应 S3.3 开放问题，均为 CLI 参数）：`--agreed-concurrency`（≥50）、`--agreed-tpm`（≥100M）、`--agreed-uncached-itpm`、`--load-threshold-tpm`（7 天峰值平均或约定值）、超长档流量占比（`tier_mix` 默认值在 `config.py`，可调）。

### 四、整体执行流程建议

```
供应商自测通过 → 提交 endpoint+key
   → 阶段1 工程验收（自研脚本覆盖已实现条目，1–2 天；#7/#9/#10 待原始文件与规范文档，preserve thinking 经 KVV）
   → 阶段2 精度验收（KVV + deepSWE 并行，KCB 移交，25–30 并发）
   → 阶段3 压力测试（50+ 并发 / TPM≥100M / 24h，Moonshot 执行）
   → 全部通过 → 上线，进入合同期 SLA/RTO/cache 结算考核
```

任一阶段不通过 → 输出问题清单 → 供应商整改 → 回归复测（精度问题需全量重跑 KVV）。
