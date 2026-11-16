# kimi-serving-test

Kimi model serving verify test — K3.1 流量外采供应商 Serving 验收测试工程。

## 目录结构

```
├── run_tests.py            # 主入口（分发各测试套件）
├── requirements.txt
├── serving_requirements.md # K3.1 要求分析归纳与测试实现方案
├── engineering/            # 工程验收（自研，条目对齐原始需求文档）
│   ├── core/               #   框架：配置 / HTTP 客户端 / 用例记录 / HTML 报告
│   ├── data/               #   附件用例（本地放置，不入库，见「数据文件准备」）
│   └── tests/              #   test_00–test_13（编号 = 截图条目号；#7/#9/#10/#13 为 pending 占位）
├── stress/                 # 压力测试（P0 基线→P1 爬坡→P2 平台→P3 脉冲）
│   ├── run_stress.py       #   CLI 入口
│   └── core/               #   合同阈值 / 流量模型 / 异步引擎 / 窗口聚合判定 / 报告
├── test-resource/          # 原始下载的需求附件（本地放置，不入库）
├── reports/                # 测试报告输出（gitignore）
└── （预留）kvv/            # KVV 精度测试
```

## 环境准备

### 通用（两个套件共用）

使用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境（推荐，速度快）：

```bash
# 安装 uv（已装可跳过）：Windows PowerShell
irm https://astral.sh/uv/install.ps1 | iex
# 或：pip install uv

# 创建虚拟环境并安装依赖（httpx + pytest；压测引擎只用标准库 asyncio + httpx）
uv venv --python 3.11                 # 任意 ≥3.10 的 Python 均可
.\.venv\Scripts\Activate.ps1          # Windows；Linux/Mac: source .venv/bin/activate
uv pip install -r requirements.txt
```

替代方式（标准库）：

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- Python ≥ 3.10；
- 通用配置：CLI 参数或环境变量 `KST_BASE_URL` / `KST_API_KEY` / `KST_MODEL`（工程验收与压力测试均读取）。

### 工程验收

- 供应商 endpoint + API key + 模型名；
- 图片用例依赖 Moonshot 图床 URL（有效期至 **2027-03-18**），过期需替换 `engineering/data/` 用例中的图源；
- 可选：`--official-base-url/--official-api-key/--official-model` 用于 #4(System Prompt)官方基线对照。

### 数据文件准备（首次 clone 后必做）

测试用例数据文件（图片 25 条、OpenClaw 12 条）**不入库**（轨迹内容含第三方凭据，且为 in-house 数据，会被 GitHub Push Protection 拦截）。clone 仓库后需手动获取并放置：

```
engineering/data/
├── 9.openclaw_cases12.jsonl              # OpenClaw 12 条
└── vendor-img-testcases-inhouse-3.jsonl  # 图片 25 条
```

获取方式：从需求文档（飞书 wiki《K3.1 流量外采要求》）的附件下载两个 jsonl，拷入 `engineering/data/` 目录即可（文件名须与上表一致，`test_05_image_cases` / `test_12_openclaw_cases` 模块运行时读取）。

> 安全提示：附件轨迹中包含第三方凭据（Lark App Secret、API Key），请勿将数据文件提交到任何远端仓库；该问题已反馈 Kimi 团队轮换凭据。

### 压力测试（压测前必须准备）

1. **约定量参数确认**（压测条款"约定量"，需与 Kimi 团队确认后代入）：
   `--agreed-concurrency`（≥50）、`--agreed-tpm`（≥100M）、`--agreed-uncached-itpm`、`--load-threshold-tpm`（7 天每分钟峰值平均，或默认回退为 agreed-tpm）。
2. **压测机（负载发生器）要求**：
   - 单进程 asyncio 即可驱动约定并发，但需核算**网络带宽**：TPM 档位的 prompt 体积大（如 256k-1m 档单请求约 400KB+），按 目标TPM × 平均 prompt 大小 估算出入向带宽，必要时多台压测机分担；
   - 文件描述符/连接数上限 ≥ 并发数 × 2 + 余量（Linux 调 `ulimit -n`；Windows 默认够用）；
   - 压测机与供应商 endpoint 之间网络质量会直接影响 TTFT 测量，建议同区域/低时延链路，并在报告 meta 中记录压测机位置。
3. **供应商侧准备**：按压力测试条款准备充足资源（并发/总 TPM/uncached ITPM ≥ 约定量、可持续 24h）；约定 RTO 演练配合人（P4 需供应商摘流）；确认闭源测试数据合规约定。
4. **时间窗口安排**：24h 平台期应覆盖高峰（08:00–24:00）与低峰（00:00–08:00）两段（若做 RTO 演练，跨时段按故障起始时段判定）。
5. **图片源**：压测 image 场景缺省复用工程验收图片 URL（同受 2027-03-18 有效期约束），也可用 `--image-url` 多次指定自备图床。
6. **先自检再长跑**：正式 24h 前，先用 demo 参数对供应商做小流量自检（`--window-s 600 --platform-duration 300` 或 README 中的 demo 命令），确认监控链路、判定口径、报告产出全部正常。

## 快速开始

```bash
# 环境准备见上一节（venv + pip install -r requirements.txt）
# 配置（CLI 参数或环境变量 KST_BASE_URL / KST_API_KEY / KST_MODEL）
python run_tests.py engineering \
    --base-url https://vendor.example.com/v1 \
    --api-key sk-xxx \
    --model kimi-k3.1
```

运行后报告自动生成于 `reports/engineering_<时间戳>/`：
- `report.html` — 单文件 HTML 报告（汇总 + 每个用例的请求/响应/断言/curl 复现命令，可过滤/搜索）
- `report_data.json` — 全量结构化数据（HTML 中超长字段的完整内容在此）

## 工程验收（engineering）覆盖项

验收条目对齐《K3.1 流量外采要求》"K3.1 Test results → 一、工程验收"表格（截图 OCR 还原，详见 serving_requirements.md）。**模块编号与截图条目序号一一对应**；标 ⏸ 的条目暂未实现（待用例文件/规范文档），测试报告中以 **SKIPPED + 原因**显式占位标注，不会静默缺失：

| 模块 | 条目 | 验收点 |
|---|---|---|
| test_00_smoke_connectivity | （前置冒烟，非条目） | /models、最小 chat、错误 key、未知模型、128 字符工具名 |
| test_01_thinking_mode | #1 | Thinking Mode Activation（anthropic style，默认 enabled，含 disabled/流式） |
| test_02_param_defaults | #2 | 参数默认值与官方一致；非默认值必须 HTTP 4xx；logprobs 分布指纹对照 |
| test_03_max_tokens_default | #3 | max_tokens 默认 131072、显式修改生效、heavy 全量验证 |
| test_04_no_system_prompt | #4 | 默认不添加 System Prompt（身份探针/泄露探针/官方对照） |
| test_05_image_cases | #5 | 图片用例 25 条回放（native + flipped stream，千图上限） |
| test_06_trace_id | #6 | traceparent 头受理 + trace 标识回传检查 |
| test_07_token_statistics ⏸ | #7 | Token 统计按 model_id 分类（月度/季度对账）：功能性验收无用例文件，待供应商统计接口文档；SKIPPED+原因 占位 |
| test_08_provider_deploy_id | #8 | 响应头 X-Msh-ProviderDeployId 存在且非空（流式/非流式） |
| test_09_streaming_output_spec ⏸ | #9 | Streaming Output Spec P0/P1：待规范文档；报告中以 SKIPPED+原因 占位标注 |
| test_10_new_model_spec ⏸ | #10 | New Model Spec（K3.1 新功能）：待规范文档；报告中以 SKIPPED+原因 占位标注 |
| test_11_thinking_effort | 补充（上线前#2） | effort low/high/max 三档、默认 max（问模型档位硬校验） |
| test_12_openclaw_cases | 补充（上线前#7） | OpenClaw 用例 12 条回放（finish_reason=tool_calls） |
| test_13_preserve_thinking ⏸ | 补充（上线前#9） | Preserve thinking：经 KVV 单独测试；报告中以 SKIPPED+原因 占位标注 |

### 常用选项

```
--timeout 600             单请求读超时（秒）
--include-heavy           运行重负载用例（#3 全量 131072 生成、#5 千图 flipped 等）
--official-base-url/--official-api-key/--official-model   #5 官方基线对照（可选）
--report-dir DIR          报告输出目录（默认 reports/）
```

示例：只跑图片（#5）与 OpenClaw（补充）用例

```bash
python run_tests.py engineering -k "test_05 or test_12" --base-url ... --api-key ... --model ...
```

## 压力测试（stress）

按客户需求文档合同指标实现（TTFT 五档、OTPS>30/1%、立即 429、10min 窗口 SLA、质量四项、24h 平台）：

```bash
# 真实 24h 压测（约定量需与 Kimi 团队确认）
python run_tests.py stress --base-url https://vendor/v1 --api-key sk-xxx --model <模型> \
    --phase full \
    --agreed-concurrency 50 --agreed-tpm 100000000 --agreed-uncached-itpm <约定值> \
    --load-threshold-tpm <7天峰值平均> \
    --platform-duration 86400 --spike-duration 120
```

- 阶段：`baseline`(P0 各档 uncached 探针) → `ramp`(P1 爬坡) → `platform`(P2 约定并发 24h+判定) → `spike`(P3 超量脉冲验证立即 429)；`full` 全流程
- 产出：`reports/stress_<时间戳>/`：`report.html`（判定矩阵/窗口明细/曲线/质量事故）、`summary.json`、`windows.json`（窗口快照，长跑中断不丢）、`metrics.jsonl`（逐请求指标，无原始请求/响应，闭源合规）、`quality_incidents.json`
- 判定：容量无 >10min 塌陷 / TTFT 分档窗口达标 / OTPS 超标 ≤1% / 失败率 <1%（TPM 阈值内外口径）/ 429 时延 P90 ≤5s / 质量四项零事故；判定失败退出码非 0
- RTO 演练（P4）需供应商配合摘流，以 platform 窗口失败率曲线人工对照（高峰 ≤10min / 低峰 ≤60min）
- demo 验证：`--window-s 10 --prompt-scale 0.001 --platform-duration 20 --spike-duration 6 --ramp-stages "warm:5:4,climb:5:8"`

## 注意

- 图片用例的 HTTP 图片 URL 有效期至 **2027-03-18**，过期后需替换图床。
- 压力测试套件已实现（见上节）；KVV 精度测试为后续扩展套件（`kvv`），入口已预留。
- 环境变量 `KST_BASE_URL` / `KST_API_KEY` / `KST_MODEL` 对 engineering 与 stress 两个套件均生效。
