#!/usr/bin/env bash
# 测试套件执行入口（Jenkins 与本地共用）。
#
# 必需环境变量：SUITE / KST_BASE_URL / KST_API_KEY / KST_MODEL / KST_OUT_DIR
# 工程验收可选：ENG_FILTER / ENG_INCLUDE_HEAVY / OFFICIAL_BASE_URL / OFFICIAL_API_KEY / OFFICIAL_MODEL
# 压力测试可选：STRESS_PHASE / AGREED_CONCURRENCY / AGREED_TPM / AGREED_UNCACHED_ITPM /
#               LOAD_THRESHOLD_TPM / PLATFORM_DURATION / SPIKE_DURATION / SPIKE_CONCURRENCY /
#               WINDOW_S / PROMPT_SCALE / RAMP_STAGES
set -u
cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

: "${SUITE:?missing SUITE}"
: "${KST_BASE_URL:?missing KST_BASE_URL}"
: "${KST_API_KEY:?missing KST_API_KEY}"
: "${KST_MODEL:?missing KST_MODEL}"
: "${KST_OUT_DIR:?missing KST_OUT_DIR}"
mkdir -p "${KST_OUT_DIR}"

ARGS=(--base-url "${KST_BASE_URL}" --api-key "${KST_API_KEY}" --model "${KST_MODEL}"
      --report-dir "${KST_OUT_DIR}")

if [ "${SUITE}" = "engineering" ] || [ "${SUITE}" = "k31selfcheck" ] || [ "${SUITE}" = "k31selfcheck2" ]; then
    if [ -n "${ENG_FILTER:-}" ]; then
        ARGS=(-k "${ENG_FILTER}" "${ARGS[@]}")
    fi
    if [ "${ENG_INCLUDE_HEAVY:-false}" = "true" ]; then
        ARGS+=(--include-heavy)
    fi
    if [ -n "${OFFICIAL_BASE_URL:-}" ]; then
        ARGS+=(--official-base-url "${OFFICIAL_BASE_URL}")
    fi
    if [ -n "${OFFICIAL_API_KEY:-}" ]; then
        ARGS+=(--official-api-key "${OFFICIAL_API_KEY}")
    fi
    if [ -n "${OFFICIAL_MODEL:-}" ]; then
        ARGS+=(--official-model "${OFFICIAL_MODEL}")
    fi
elif [ "${SUITE}" = "stress" ]; then
    ARGS+=(--phase "${STRESS_PHASE:-full}")
    ARGS+=(--agreed-concurrency "${AGREED_CONCURRENCY:-50}")
    ARGS+=(--agreed-tpm "${AGREED_TPM:-100000000}")
    ARGS+=(--agreed-uncached-itpm "${AGREED_UNCACHED_ITPM:-0}")
    ARGS+=(--load-threshold-tpm "${LOAD_THRESHOLD_TPM:-0}")
    # 默认值与 stress/core/config.py 原始默认严格一致（触发层不改写测试行为）
    ARGS+=(--platform-duration "${PLATFORM_DURATION:-86400}")
    ARGS+=(--spike-duration "${SPIKE_DURATION:-120}")
    ARGS+=(--spike-concurrency "${SPIKE_CONCURRENCY:-0}")
    ARGS+=(--window-s "${WINDOW_S:-600}")
    ARGS+=(--prompt-scale "${PROMPT_SCALE:-1.0}")
    if [ -n "${RAMP_STAGES:-}" ]; then
        ARGS+=(--ramp-stages "${RAMP_STAGES}")
    fi
else
    echo "未知 SUITE: ${SUITE}（支持 engineering / k31selfcheck / k31selfcheck2 / stress）" >&2
    exit 2
fi

echo "[run_suite] python run_tests.py ${SUITE} ${ARGS[*]}"
RC=0
python run_tests.py "${SUITE}" "${ARGS[@]}" || RC=$?

python scripts/gen_stats.py "${KST_OUT_DIR}" "${SUITE}" "${RC}"
echo "[run_suite] suite=${SUITE} exit_code=${RC}"
exit "${RC}"
