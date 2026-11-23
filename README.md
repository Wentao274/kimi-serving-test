# kimi-serving-test

Kimi model serving verify test — K3.1 流量外采供应商 Serving 验收测试工程。

## 目录结构

```
├── run_tests.py            # 主入口（分发各测试套件）
├── requirements.txt
├── serving_requirements.md # K3.1 要求分析（内部资料，不入库，仅本地）
├── Jenkinsfile             # Jenkins 远程触发流水线（SUITE choice 分流，不改测试逻辑）
├── scripts/                # 触发层辅助（run_suite.sh 参数透传 / gen_stats.py 统计）
├── engineering/            # 工程验收（自研，条目对齐原始需求文档）
│   ├── core/               #   框架：配置 / HTTP 客户端 / 用例记录 / HTML 报告
│   ├── data/               #   附件用例（本地放置，不入库，见「数据文件准备」）
│   └── tests/              #   test_00–test_13（编号 = 截图条目号；#7/#9/#10 为 pending 占位）
├── k31selfcheck/           # K3.1-Pro 供应商自测基线（功能兼容性 14 项，三协议 Chat/Responses/Messages）
│   ├── protocols.py        #   三协议客户端（含 SSE 事件采集）
│   └── tests/              #   test_k01–test_k14（编号 = 基线测试点序号）
├── k31selfcheck2/          # 模型接入要求（对外版）功能测试（3.1/3.2，92 用例）
│   └── tests/              #   test_31_xx / test_32_xx（编号 = 文档测试点序号）
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

## 执行方式（两种，测试逻辑完全一致）

| | 方式一：手动执行 | 方式二：Jenkins 远程触发 |
|---|---|---|
| 入口 | `python run_tests.py <suite> [args]` | 根目录 `Jenkinsfile`（SUITE choice 分流） |
| 适用 | 本地/任意机器调试、单次验证、demo 自检 | 定时/远程批量验收、24h 压测、报告邮件分发 |
| 触发 | 命令行直接运行（见「快速开始」「工程验收」「压力测试」节） | `buildWithParameters` API 或 Jenkins 页面点构建（见「Jenkins 远程触发」节） |
| 报告 | `reports/<suite>_<时间戳>/` | 远程机 `builds/<suite>/<tester>/<model>/<构建号>/` + 邮件附件 |

> 两种方式最终调用的是**同一套测试代码**（Jenkins 经 `scripts/run_suite.sh` 透传参数调用同一个 `run_tests.py`），断言、阈值、判定、报告格式无任何差异。

## 快速开始（方式一：手动执行）

```bash
# 环境准备见上一节（venv + pip install -r requirements.txt）
# 配置（CLI 参数或环境变量 KST_BASE_URL / KST_API_KEY / KST_MODEL）
python run_tests.py engineering \
    --base-url https://vendor.example.com/v1 \
    --api-key sk-xxx \
    --model kimi-k3.1
```

运行后报告自动生成于 `reports/engineering_<时间戳>/`：
- `<model>_report_<时间戳>.html`（如 `kimi-k3.1_report_20261118102035.html`）— 单文件 HTML 报告（汇总 + 每个用例的请求/响应/断言/curl 复现命令，可过滤/搜索）
- `report_data.json` — 全量结构化数据（HTML 中超长字段的完整内容在此）

**官方双跑对比报告**：开启 `COMPARE_OFFICIAL` 后，`scripts/gen_compare.py` 生成 `<model>_compare_<时间戳>.html`——左右双通道布局（左栏供应商用例状态/请求响应详情，右栏官方同例详情），顶部含「供应商 vs 官方 对比汇总」统计，支持"仅看不一致"过滤。

## 工程验收（engineering）覆盖项

验收条目对齐《K3.1 流量外采要求》"K3.1 Test results → 一、工程验收"表格（截图 OCR 还原，详见本地文档 serving_requirements.md（内部资料，不入库））。**模块编号与截图条目序号一一对应**；标 ⏸ 的条目暂未实现（待用例文件/规范文档），测试报告中以 **SKIPPED + 原因**显式占位标注，不会静默缺失：

| 模块 | 条目 | 验收点 |
|---|---|---|
| test_00_smoke_connectivity | （前置冒烟，非条目） | /models、最小 chat、错误 key、未知模型、128 字符工具名 |
| test_01_thinking_mode | #1 | Thinking Mode Activation（anthropic style，默认 enabled，含 disabled/流式） |
| test_02_param_defaults | #2 | 参数默认值与官方一致；非默认值必须 HTTP 4xx；logprobs 分布指纹对照 |
| test_03_max_tokens_default | #3 | max_tokens 默认 131072、显式修改生效、heavy 计数序列上限验证（模型提前 stop 记无法判定、自动换措辞重试） |
| test_04_no_system_prompt | #4 | 默认不添加 System Prompt（身份探针/泄露探针/官方对照） |
| test_05_image_cases | #5 | 图片用例 25 条回放（native + flipped stream，千图上限）+ 7 种图片格式覆盖（jpeg/png/gif/tiff/bmp/webp/heic，本地生成 base64 小图） |
| test_06_trace_id | #6 | traceparent 头受理 + trace 标识回传检查 |
| test_07_token_statistics ⏸ | #7 | Token 统计按 model_id 分类（月度/季度对账）：功能性验收无用例文件，待供应商统计接口文档；SKIPPED+原因 占位 |
| test_08_provider_deploy_id | #8 | 响应头 X-Msh-ProviderDeployId 存在且非空（流式/非流式） |
| test_09_streaming_output_spec ⏸ | #9 | Streaming Output Spec P0/P1：待规范文档；报告中以 SKIPPED+原因 占位标注 |
| test_10_new_model_spec ⏸ | #10 | New Model Spec（K3.1 新功能）：待规范文档；报告中以 SKIPPED+原因 占位标注 |
| test_11_thinking_effort | 补充（上线前#2） | effort low/high/max 三档、默认 max（接受性 + reasoning_content 硬校验；模型自述档位为 soft，仅官方平台可靠） |
| test_12_openclaw_cases | 补充（上线前#7） | OpenClaw 用例 12 条回放（finish_reason=tool_calls；stream=false 时自动剥离 stream_options 并标注） |
| test_13_preserve_thinking | 补充（上线前#9） | Preserve thinking 锚点验证：prompt_tokens=160 + 5 数字完全一致；不传 keep 对照（soft） |

### 常用选项

```
--timeout 600             单请求读超时（秒）
--include-heavy           运行重负载用例（#3 计数序列上限验证、#5 千图 flipped 等）
                          （Jenkins 拆分为 VENDOR_INCLUDE_HEAVY / OFFICIAL_INCLUDE_HEAVY 双侧独立开关，
                            官方侧不开启时其 heavy 用例标记为 SKIPPED 跳过）
--official-base-url/--official-api-key/--official-model   #5 官方基线对照（可选）
--report-dir DIR          报告输出目录（默认 reports/）
```

示例：只跑图片（#5）与 OpenClaw（补充）用例

```bash
python run_tests.py engineering -k "test_05 or test_12" --base-url ... --api-key ... --model ...
```

## K3.1-Pro 自测基线（k31selfcheck）

依据《Kimi-K3.1-Pro 供应商自测基线标准》「二、功能兼容性要求」14 个测试点实现，覆盖三协议（Chat `/v1/chat/completions`、Responses `/v1/responses`、Messages `/anthropic/v1/messages`）：

```bash
python run_tests.py k31selfcheck \
    --base-url https://vendor.example.com/v1 --api-key sk-xxx --model kimi-k3.1
```

- 报告：`reports/k31selfcheck_<时间戳>/<model>_selfcheck_report_<时间戳>.html`（与工程验收同格式）+ `report_data.json`
- 14 个测试点：三协议与响应格式、usage 与缓存计量、常驻思考与推理强度、采样与输出预算、流式状态机、结构化输出、工具调用与多步闭环、错误码、参数与输入边界、可观测性、超时与长任务（heavy）、图片多模态、输入 Token 对齐（需 `--official-*`）、消息历史与思考回填
- 协议未开放（Responses/Messages 4xx）按基线"不得以其他协议结果替代"记为失败并注明；官方对照需 `--official-base-url/--official-api-key/--official-model`
- Jenkins：`SUITE=k31selfcheck` 直接触发（同一 Jenkinsfile)

## 模型接入功能测试（k31selfcheck2）

依据《模型接入要求（对外版）》「3. 功能」实现：3.1 整体基本要求（11 项）+ 3.2 API 功能测试（18 项），共 92 用例。默认值与预期行为按 kimi-k3.1-pro 官方规格对齐：

- thinking：enabled/disabled 均支持、默认 enabled；effort 三档 low/high/max（thinking.effort）、默认 max
- max_tokens：默认/上限 131072，显式传 >131072 拒绝（400）
- temperature：thinking 模式允许 {0, 0.6, 1.0}，disabled 仅 {0.6}，违规 400 / immutable_param；top_p=0.95、presence_penalty=0、frequency_penalty=0 仅接受官方默认值

```bash
python run_tests.py k31selfcheck2 \
    --base-url https://vendor.example.com/v1 --api-key sk-xxx --model kimi-k3.1
# 重负载用例（默认跳过，需 --include-heavy）：
python run_tests.py k31selfcheck2 --base-url ... --api-key ... --model ... --include-heavy
```

- 报告：`reports/k31selfcheck2_<时间戳>/<model>_selfcheck2_report_<时间戳>.html` + `report_data.json`
- heavy 用例 3 个：不传 max_tokens 默认上限 131072 计数序列验证（约 70+ 分钟/次）、缓存 TTL 过期探测（等待时长 `KST_CACHE_TTL_WAIT_S` 可调，默认 310s）、~1M tokens 上下文接入
- Token 计数官方对照需 `--official-base-url/--official-api-key/--official-model`（未配置则该用例跳过）
- Jenkins：`SUITE=k31selfcheck2` 直接触发（同一 Jenkinsfile）

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
- 注：质量判定严格对应文档四项（字符重复/工具调用重复/串台/无意义输出）；claw 场景的 finish_reason 不作质量判据（工程验收 `test_12_openclaw_cases` 已专项覆盖 finish=tool_calls 校验），各请求 finish_reason 分布保留在 `metrics.jsonl` 供离线分析
- RTO 演练（P4）需供应商配合摘流，以 platform 窗口失败率曲线人工对照（高峰 ≤10min / 低峰 ≤60min）
- demo 验证：`--window-s 10 --prompt-scale 0.001 --platform-duration 20 --spike-duration 6 --ramp-stages "warm:5:4,climb:5:8"`

## Jenkins 远程触发（方式二：engineering / stress 共用流水线）

根目录 `Jenkinsfile` 为两套件共用的声明式流水线（结构参照 Kimi-Vendor-Verifier），通过 **SUITE choice 参数**分流：

| 方式 | 说明 |
|---|---|
| `SUITE=engineering` | 工程验收（pytest），参数：`ENG_FILTER`（-k 过滤）、`INCLUDE_HEAVY`、`OFFICIAL_*`、`COMPARE_OFFICIAL`（官方双跑对比，默认关）、`COMPARE_FILTER`（对比范围，空=全量，示例 `"test_05 or test_12"`） |
| `SUITE=k31selfcheck` / `SUITE=k31selfcheck2` | 供应商自测基线 / 模型接入功能测试（对外版 3.1/3.2），参数：`ENG_FILTER`、`VENDOR_INCLUDE_HEAVY`（heavy 用例）、`OFFICIAL_*`（官方对照） |
| `SUITE=stress` | 压力测试，参数：`STRESS_PHASE`、`AGREED_*`、`LOAD_THRESHOLD_TPM`、`PLATFORM_DURATION`（默认 86400=24h，与套件原始默认一致；短时验证显式填小）、`SPIKE_*`、`WINDOW_S`、`PROMPT_SCALE`、`RAMP_STAGES` |

流水线执行（master → SSH 远程测试机）：打印参数 → API 连通性预检（失败即终止后续）→ 环境检查（清残留进程 / git pull 并**记录代码版本** / uv venv / engineering 数据文件检查）→ 按 SUITE 运行 → 报告拉取 → 邮件（**正文仅汇总统计 + 测试代码版本，报告 HTML 以原格式作为附件发送；git pull 失败时邮件醒目告警**）→ 保留最近 20 构建。报告输出在远程机 `builds/<suite>/<tester>/<model>/<构建号>/`（engineering 与 stress 分目录）。

### Jenkins job 配置（一次性）

1. 新建 **Pipeline** job → Pipeline definition 选 **Pipeline script from SCM**：填本仓库地址与凭据，Script Path 填 `Jenkinsfile`；
2. 勾选「**触发远程构建**」（Build Triggers → Trigger builds remotely），设置 Authentication Token（如 `kst-trigger-token`）；
3. 确认远程测试机已按「环境准备」放置 `engineering/data/` 数据文件（engineering 套件必需，流水线会检查）。

### 远程触发命令

```bash
# 工程验收（全量）
curl -X POST "https://<jenkins>/job/<job-name>/buildWithParameters?token=kst-trigger-token" \
    --user "<user>:<api-token>" \
    --data-urlencode "SUITE=engineering" \
    --data-urlencode "MODEL=kimi-k3.1" \
    --data-urlencode "BASE_URL=https://vendor.example.com" \
    --data-urlencode "API_KEY=sk-xxx" \
    --data-urlencode "TESTER=liwt"

# 压力测试（24h 平台期）
curl -X POST "https://<jenkins>/job/<job-name>/buildWithParameters?token=kst-trigger-token" \
    --user "<user>:<api-token>" \
    --data-urlencode "SUITE=stress" \
    --data-urlencode "MODEL=kimi-k3.1" \
    --data-urlencode "BASE_URL=https://vendor.example.com" \
    --data-urlencode "API_KEY=sk-xxx" \
    --data-urlencode "PLATFORM_DURATION=86400" \
    --data-urlencode "AGREED_CONCURRENCY=50" \
    --data-urlencode "AGREED_TPM=100000000"
```

> 本地脚本 `scripts/run_suite.sh` + `scripts/gen_stats.py` 与 Jenkins 解耦，也可在任意 Linux 机器上手动 `export` 对应环境变量后执行同一入口。
>
> **官方双跑对比（COMPARE_OFFICIAL）**：开启且配置 `OFFICIAL_*` 后，工程验收全量用例在官方渠道再执行一遍（与供应商同口径，`COMPARE_FILTER` 可收窄范围），`scripts/gen_compare.py` 逐用例生成对比（双边均通过 / 仅供应商失败 / 仅官方失败 / 双边均失败），邮件正文附对比汇总表，附件含两侧 report.html 与 compare.html。

## 注意

- 图片用例的 HTTP 图片 URL 有效期至 **2027-03-18**，过期后需替换图床。
- 压力测试套件已实现（见上节）；KVV 精度测试为后续扩展套件（`kvv`），入口已预留。
- 环境变量 `KST_BASE_URL` / `KST_API_KEY` / `KST_MODEL` 对 engineering 与 stress 两个套件均生效。
