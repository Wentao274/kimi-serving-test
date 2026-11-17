pipeline {
    agent {
        label 'master'
    }

    options {
        // 串行化构建：压测会打满供应商容量，并发构建会互相污染 TTFT/429 数据
        disableConcurrentBuilds()
    }

    parameters {
        choice(name: 'SUITE', choices: ['engineering', 'stress'], description: '测试套件：engineering=工程验收（条目 #1-#10+补充条目，pytest）；stress=压力测试（P0基线→P1爬坡→P2平台→P3脉冲）')
        string(name: 'TESTER', defaultValue: 'liwt', description: '测试人员名称（必填）')
        string(name: 'MODEL', defaultValue: 'kimi-k3.1', description: '被测供应商模型名（必填，即 /v1/models 返回的 id 或供应商约定名）')
        string(name: 'BASE_URL', defaultValue: 'https://vendor.example.com', description: '供应商 API 根地址（必填，可不带 /v1，流水线自动拼接）')
        password(name: 'API_KEY', defaultValue: '', description: '供应商 API Key（必填）')

        // ---------------- 工程验收（SUITE=engineering 时生效） ----------------
        string(name: 'ENG_FILTER', defaultValue: '', description: '工程验收：pytest -k 过滤表达式（空=全量），如 "test_05 or test_12"、"test_01"')
        booleanParam(name: 'INCLUDE_HEAVY', defaultValue: false, description: '工程验收：运行重负载用例（#3 全量 131072 生成约70分钟、#5 千图 flipped）')
        string(name: 'OFFICIAL_BASE_URL', defaultValue: '', description: '工程验收（可选）：官方 API 根地址，用于 #4 System Prompt 官方基线对照')
        password(name: 'OFFICIAL_API_KEY', defaultValue: '', description: '工程验收（可选）：官方 API Key')
        string(name: 'OFFICIAL_MODEL', defaultValue: '', description: '工程验收（可选）：官方模型名')

        // ---------------- 压力测试（SUITE=stress 时生效） ----------------
        choice(name: 'STRESS_PHASE', choices: ['full', 'baseline', 'ramp', 'platform', 'spike'], description: '压测阶段：full=P0基线→P1爬坡→P2平台→P3脉冲全流程')
        string(name: 'AGREED_CONCURRENCY', defaultValue: '50', description: '压测：约定并发量（条款要求测试期 ≥50）')
        string(name: 'AGREED_TPM', defaultValue: '100000000', description: '压测：约定总 TPM（条款要求测试期 ≥100M）')
        string(name: 'AGREED_UNCACHED_ITPM', defaultValue: '0', description: '压测：约定 uncached ITPM（0=不参与判定）')
        string(name: 'LOAD_THRESHOLD_TPM', defaultValue: '0', description: '压测：负载阈值 TPM（7天每分钟峰值平均；0=回退为 AGREED_TPM）')
        string(name: 'PLATFORM_DURATION', defaultValue: '86400', description: '压测：P2 平台期秒数（与套件原始默认一致 = 86400 即 24h；短时验证请显式改小，如 300）')
        string(name: 'SPIKE_DURATION', defaultValue: '120', description: '压测：P3 脉冲秒数（与套件原始默认一致 = 120）')
        string(name: 'SPIKE_CONCURRENCY', defaultValue: '0', description: '压测：P3 脉冲并发（0=约定并发×2）')
        string(name: 'WINDOW_S', defaultValue: '600', description: '压测：聚合窗口秒数（合同口径 600；demo 验证可调小如 60）')
        string(name: 'PROMPT_SCALE', defaultValue: '1.0', description: '压测：prompt 长度缩放（demo 用 0.001~0.01；真实压测保持 1.0）')
        string(name: 'RAMP_STAGES', defaultValue: '', description: '压测：自定义爬坡阶梯 "start:900:10,climb:900:30,peak:900:50"（空=默认三段）')

        // ---------------- 通用 ----------------
        string(name: 'DESCRIPTION', defaultValue: '', description: '被测服务的描述信息（仅用于邮件展示）')
        text(name: 'RECIPIENTS', defaultValue: 'liwt@zetyun.com', description: '测试报告邮件接收者（逗号分隔）')
        string(name: 'WORK_DIR', defaultValue: '/dingofs/data2/userdata/liwt/maas-image/kimi-serving-test', description: '远程测试机上的仓库目录，请不要改动')
    }

    environment {
        SSH_CREDENTIALS = 'HOST_SSH_KEY'
        REMOTE_HOST = '10.201.132.50'
        REMOTE_USER = 'root'
        // 报告输出分层：builds/<suite>/<tester>/<model>/<build号>/（model 名做文件系统安全化）
        BUILD_OUTPUT_DIR = "builds/${params.SUITE}/${params.TESTER}/${params.MODEL.replaceAll('[^A-Za-z0-9._-]', '_')}/${BUILD_NUMBER}"
        // BASE_URL 幂等拼接 /v1：先剥尾斜杠 → 再剥结尾 /v1（若有）→ 统一补 /v1
        BASE_URL_V1 = "${params.BASE_URL.replaceAll('/+$', '').replaceAll('/?v1$', '')}/v1"
    }

    stages {
        stage('打印测试参数') {
            steps {
                script {
                    println("========================================")
                    println("=== K3.1 供应商验收测试参数 ===")
                    println("========================================")
                    println("测试套件:     ${params.SUITE}")
                    println("测试人员:     ${params.TESTER}")
                    println("模型名称:     ${params.MODEL}")
                    println("BASE_URL:     ${params.BASE_URL}  (→ ${env.BASE_URL_V1})")
                    if (params.SUITE == 'engineering') {
                        println("用例过滤:     ${params.ENG_FILTER ?: '(全量)'}")
                        println("重负载用例:   ${params.INCLUDE_HEAVY}")
                        println("官方对照:     ${params.OFFICIAL_BASE_URL ? params.OFFICIAL_BASE_URL : '(不启用)'}")
                    } else {
                        println("压测阶段:     ${params.STRESS_PHASE}")
                        println("约定并发:     ${params.AGREED_CONCURRENCY}")
                        println("约定TPM:      ${params.AGREED_TPM}")
                        println("uncachedITPM: ${params.AGREED_UNCACHED_ITPM}（0=不判定）")
                        println("负载阈值TPM:  ${params.LOAD_THRESHOLD_TPM}（0=回退约定TPM）")
                        println("平台期:       ${params.PLATFORM_DURATION}s")
                        println("脉冲:         ${params.SPIKE_DURATION}s @ ${params.SPIKE_CONCURRENCY == '0' ? '约定×2' : params.SPIKE_CONCURRENCY}并发")
                        println("窗口/缩放:    ${params.WINDOW_S}s / ${params.PROMPT_SCALE}")
                        println("爬坡阶梯:     ${params.RAMP_STAGES ?: '(默认三段)'}")
                    }
                    println("服务描述:     ${params.DESCRIPTION ?: '(无)'}")
                    println("邮件接收者:   ${params.RECIPIENTS}")
                    println("工作目录:     ${params.WORK_DIR}")
                    println("构建编号:     #${BUILD_NUMBER}")
                    println("========================================")
                }
            }
        }

        stage('API 连通性预检') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    script {
                        def apiKey = params.API_KEY?.toString()?.trim()
                        if (!apiKey) { apiKey = 'EMPTY' }
                        try {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -o pipefail
{
    echo "=== 检查 API 连通性 (/v1/models) ==="
    HTTP_CODE=\$(curl -s --connect-timeout 10 -m 30 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${apiKey}" ${env.BASE_URL_V1}/models)
    if [ "\${HTTP_CODE}" != "200" ]; then
        echo "ERROR: API 连通性检查失败, HTTP状态码: \${HTTP_CODE}, URL: ${env.BASE_URL_V1}/models"
        exit 1
    fi
    echo "API /models 连通性检查通过, HTTP状态码: \${HTTP_CODE}"

    echo "=== 检查 Chat Completions 接口 ==="
    CHAT_RESP=\$(curl -s --connect-timeout 10 -m 60 -w "\\n%{http_code}" ${env.BASE_URL_V1}/chat/completions \\
        -H "Content-Type: application/json" \\
        -H "Authorization: Bearer ${apiKey}" \\
        -d '{"model":"${params.MODEL}","messages":[{"role":"user","content":"hello"}],"max_tokens":10}')
    CHAT_HTTP_CODE=\$(echo "\${CHAT_RESP}" | tail -1)
    if [ "\${CHAT_HTTP_CODE}" != "200" ]; then
        echo "ERROR: Chat Completions 接口检查失败, HTTP状态码: \${CHAT_HTTP_CODE}"
        echo "响应内容: \$(echo "\${CHAT_RESP}" | head -n -1)"
        exit 1
    fi
    echo "Chat Completions 接口检查通过, HTTP状态码: \${CHAT_HTTP_CODE}"
} 2>&1 | tee /tmp/kst_connectivity_${BUILD_NUMBER}.log
ENDSSH
"""
                        } catch (Exception e) {
                            env.CONNECTIVITY_FAILED = 'true'
                            currentBuild.result = 'UNSTABLE'
                            println("=== API 连通性预检失败,后续阶段将跳过 ===")
                        }
                    }
                }
            }
        }

        stage('环境检查') {
            when {
                expression { env.CONNECTIVITY_FAILED != 'true' }
            }
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
cd ${params.WORK_DIR}
echo "工作目录: \$(pwd)"

echo "=== 清理残留测试进程 ==="
RESIDUAL=\$(pgrep -af "run_tests\\.py|run_suite\\.sh|run_stress" 2>/dev/null | grep -vE "jenkins|durable|@tmp" || true)
if [ -n "\${RESIDUAL}" ]; then
    echo "发现残留进程:"
    echo "\${RESIDUAL}"
    echo "\${RESIDUAL}" | awk '{print \$1}' | xargs -r kill -TERM 2>/dev/null || true
    sleep 3
    REMAINING=\$(pgrep -af "run_tests\\.py|run_suite\\.sh|run_stress" 2>/dev/null | grep -vE "jenkins|durable|@tmp" || true)
    if [ -n "\${REMAINING}" ]; then
        echo "未响应 SIGTERM,发送 SIGKILL..."
        echo "\${REMAINING}" | awk '{print \$1}' | xargs -r kill -KILL 2>/dev/null || true
        sleep 1
    fi
    echo "残留进程清理完成"
else
    echo "未发现残留进程"
fi

echo "=== 同步代码 ==="
mkdir -p ${BUILD_OUTPUT_DIR}
BEFORE=\$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
echo "同步前代码: \${BEFORE}"
SYNC_STATUS="ok"
git pull --ff-only || SYNC_STATUS="failed"
AFTER=\$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
echo "同步后代码: \${AFTER} (git pull: \${SYNC_STATUS})"
{
    echo "githash=\${AFTER}"
    echo "gitbefore=\${BEFORE}"
    echo "gitsync=\${SYNC_STATUS}"
} > ${BUILD_OUTPUT_DIR}/code_version.properties
if [ "\${SYNC_STATUS}" = "failed" ]; then
    echo "警告: git pull 失败，本次将使用旧代码 \${AFTER} 继续测试（结果按旧代码口径）"
fi

echo "=== 检查并创建虚拟环境 ==="
if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，创建虚拟环境..."
    uv venv
fi
source .venv/bin/activate
uv pip install -r requirements.txt
deactivate

if [ "${params.SUITE}" = "engineering" ]; then
    echo "=== 检查工程验收数据文件（不入库，需预先放置） ==="
    for f in engineering/data/9.openclaw_cases12.jsonl engineering/data/vendor-img-testcases-inhouse-3.jsonl; do
        if [ ! -f "\$f" ]; then
            echo "ERROR: 缺少数据文件 \$f"
            echo "请按 README「数据文件准备」将飞书附件拷入 engineering/data/ 后重跑"
            exit 1
        fi
    done
    echo "数据文件检查通过"
fi
echo "=== 环境检查完成 ==="
ENDSSH"""
                }
            }
        }

        stage('运行工程验收测试') {
            when {
                expression { env.CONNECTIVITY_FAILED != 'true' && params.SUITE == 'engineering' }
            }
            steps {
                script {
                    def apiKey = params.API_KEY?.toString()?.trim()
                    if (!apiKey) { apiKey = 'EMPTY' }
                    def officialKey = params.OFFICIAL_API_KEY?.toString()?.trim() ?: ''
                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
cd ${params.WORK_DIR}
mkdir -p ${BUILD_OUTPUT_DIR}

export SUITE="engineering"
export KST_BASE_URL="${env.BASE_URL_V1}"
export KST_API_KEY="${apiKey}"
export KST_MODEL="${params.MODEL}"
export KST_OUT_DIR="${params.WORK_DIR}/${BUILD_OUTPUT_DIR}"
export ENG_FILTER="${params.ENG_FILTER}"
export ENG_INCLUDE_HEAVY="${params.INCLUDE_HEAVY}"
export OFFICIAL_BASE_URL="${params.OFFICIAL_BASE_URL}"
export OFFICIAL_API_KEY="${officialKey}"
export OFFICIAL_MODEL="${params.OFFICIAL_MODEL}"

bash scripts/run_suite.sh
ENDSSH"""
                        }
                    }
                }
            }
        }

        stage('运行压力测试') {
            when {
                expression { env.CONNECTIVITY_FAILED != 'true' && params.SUITE == 'stress' }
            }
            steps {
                script {
                    def apiKey = params.API_KEY?.toString()?.trim()
                    if (!apiKey) { apiKey = 'EMPTY' }
                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
cd ${params.WORK_DIR}
mkdir -p ${BUILD_OUTPUT_DIR}

export SUITE="stress"
export KST_BASE_URL="${env.BASE_URL_V1}"
export KST_API_KEY="${apiKey}"
export KST_MODEL="${params.MODEL}"
export KST_OUT_DIR="${params.WORK_DIR}/${BUILD_OUTPUT_DIR}"
export STRESS_PHASE="${params.STRESS_PHASE}"
export AGREED_CONCURRENCY="${params.AGREED_CONCURRENCY}"
export AGREED_TPM="${params.AGREED_TPM}"
export AGREED_UNCACHED_ITPM="${params.AGREED_UNCACHED_ITPM}"
export LOAD_THRESHOLD_TPM="${params.LOAD_THRESHOLD_TPM}"
export PLATFORM_DURATION="${params.PLATFORM_DURATION}"
export SPIKE_DURATION="${params.SPIKE_DURATION}"
export SPIKE_CONCURRENCY="${params.SPIKE_CONCURRENCY}"
export WINDOW_S="${params.WINDOW_S}"
export PROMPT_SCALE="${params.PROMPT_SCALE}"
export RAMP_STAGES="${params.RAMP_STAGES}"

bash scripts/run_suite.sh
ENDSSH"""
                        }
                    }
                }
            }
        }

        stage('拉取报告到Jenkins') {
            when {
                expression { env.CONNECTIVITY_FAILED != 'true' }
            }
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        sh """
mkdir -p reports/${BUILD_NUMBER}
if ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "[ -d ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} ]"; then
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "tar -czf /tmp/kst_${BUILD_NUMBER}.tar.gz -C ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} ."
    scp -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST}:/tmp/kst_${BUILD_NUMBER}.tar.gz ./reports/${BUILD_NUMBER}/
    tar -xzf ./reports/${BUILD_NUMBER}/kst_${BUILD_NUMBER}.tar.gz -C ./reports/${BUILD_NUMBER}/
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "rm -f /tmp/kst_${BUILD_NUMBER}.tar.gz"
    echo "=== 拉取结果 ==="
    ls -la ./reports/${BUILD_NUMBER}/
else
    echo "警告: 远程输出目录 ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} 不存在，跳过报告拉取"
fi
"""
                    }
                }
            }
        }

        stage('发送邮件') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    script {
                        def stats = [:]
                        def statsFile = "reports/${BUILD_NUMBER}/stats.properties"
                        if (fileExists(statsFile)) {
                            readFile(file: statsFile, encoding: 'UTF-8').split('\n').each { line ->
                                def matcher = line.trim() =~ /^([A-Za-z]+)=(.*)$/
                                if (matcher.matches()) {
                                    stats[matcher.group(1)] = matcher.group(2)
                                }
                            }
                        }

                        // 测试代码版本（git pull 同步结果，环境检查阶段写入）
                        def codeVer = [:]
                        def codeVerFile = "reports/${BUILD_NUMBER}/code_version.properties"
                        if (fileExists(codeVerFile)) {
                            readFile(file: codeVerFile, encoding: 'UTF-8').split('\n').each { line ->
                                def m = line.trim() =~ /^([A-Za-z]+)=(.*)$/
                                if (m.matches()) {
                                    codeVer[m.group(1)] = m.group(2)
                                }
                            }
                        }
                        def gitSyncFailed = (codeVer.gitsync == 'failed')

                        def reportFile = sh(script: "ls reports/${BUILD_NUMBER}/engineering_*/report.html reports/${BUILD_NUMBER}/stress_*/report.html 2>/dev/null | head -1", returnStdout: true).trim()

                        // 报告 HTML 以原格式作为附件发送，邮件正文只保留汇总统计（不内嵌报告，避免邮件客户端破坏样式）
                        def fallbackStyle = "body { font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; margin: 0 auto; max-width: 1080px; padding: 20px 32px; color: #1f2937; background: #eef1f6; font-size: 14px; line-height: 1.7; }\ntable { border-collapse: collapse; width: 100%; margin: 14px 0 18px; background: #ffffff; font-size: 13px; border: 1px solid #d8dfeb; }\nth { background: #e3edfc; color: #1e3a8a; font-weight: 600; }\nth, td { border: 1px solid #d8dfeb; padding: 6px 12px; text-align: left; vertical-align: top; }\n.email-footer { margin-top: 24px; padding: 12px 15px; background-color: #f9f9f9; border-radius: 3px; color: #666; font-size: 12px; }"

                        def connectivityFailed = (env.CONNECTIVITY_FAILED == 'true')
                        def resultLabel = connectivityFailed ? '连通性预检未通过' : (stats.result ?: (currentBuild.currentResult == 'SUCCESS' ? 'PASS' : 'FAIL'))
                        def rateLabel = stats.rate ? "${stats.rate}%" : 'N/A'
                        def bannerColor = (resultLabel == 'PASS') ? '#4CAF50' : '#f44336'
                        def suiteLabel = (params.SUITE == 'engineering') ? '工程验收' : '压力测试'

                        def suiteParamsRows = ''
                        if (params.SUITE == 'engineering') {
                            suiteParamsRows = """
    <tr><th>用例过滤</th><td>${params.ENG_FILTER ?: '(全量)'}</td></tr>
    <tr><th>重负载用例</th><td>${params.INCLUDE_HEAVY}</td></tr>
    <tr><th>用例总数</th><td>${stats.total ?: 'N/A'}</td></tr>
    <tr><th>通过 / 失败</th><td>${stats.passed ?: 'N/A'} / ${stats.failed ?: 'N/A'}</td></tr>
    <tr><th>跳过 / 错误</th><td>${stats.skipped ?: 'N/A'} / ${stats.errors ?: 'N/A'}</td></tr>"""
                        } else {
                            suiteParamsRows = """
    <tr><th>压测阶段</th><td>${params.STRESS_PHASE}</td></tr>
    <tr><th>约定并发 / TPM</th><td>${params.AGREED_CONCURRENCY} / ${params.AGREED_TPM}</td></tr>
    <tr><th>平台期 / 窗口</th><td>${params.PLATFORM_DURATION}s / ${params.WINDOW_S}s</td></tr>
    <tr><th>总请求数</th><td>${stats.total ?: 'N/A'}</td></tr>
    <tr><th>判定通过 / 失败</th><td>${stats.passed ?: 'N/A'} / ${stats.failed ?: 'N/A'}</td></tr>
    <tr><th>质量事故</th><td>${stats.errors ?: 'N/A'}</td></tr>"""
                        }

                        def emailBody = """
<html>
<head>
<meta charset="utf-8">
<style>
${fallbackStyle}
</style>
</head>
<body>
<div style="background-color: ${bannerColor}; color: white; padding: 18px 20px; border-radius: 5px 5px 0 0; margin-bottom: 10px;">
    <h2 style="margin: 0;">K3.1 供应商${suiteLabel}报告 - 构建 #${BUILD_NUMBER}</h2>
</div>
${connectivityFailed ? '<div style="background-color: #d32f2f; color: white; padding: 12px 15px; border-radius: 4px; margin-bottom: 12px;"><strong>API 连通性预检未通过</strong>：本次构建未执行测试，请检查 BASE_URL / API_KEY，详见构建日志。</div>' : ''}
${gitSyncFailed ? "<div style='background-color: #ff9800; color: white; padding: 12px 15px; border-radius: 4px; margin-bottom: 12px;'><strong>git pull 同步失败</strong>：本次测试基于旧代码 ${codeVer.githash} 执行（同步前 ${codeVer.gitbefore}），结果按旧代码口径，请知悉。</div>" : ''}
<h2>Jenkins 构建信息</h2>
<table>
    <tr><th>构建编号</th><td>#${BUILD_NUMBER}</td></tr>
    <tr><th>测试人员</th><td>${params.TESTER}</td></tr>
    <tr><th>测试套件</th><td>${suiteLabel} (${params.SUITE})</td></tr>
    <tr><th>模型名称</th><td>${params.MODEL}</td></tr>
    <tr><th>API 地址</th><td>${params.BASE_URL}</td></tr>
    <tr><th>服务描述</th><td>${params.DESCRIPTION ?: '(无)'}</td></tr>
    <tr><th>测试代码版本</th><td>${codeVer.githash ?: 'N/A'}${codeVer.gitsync ? "（git pull: ${codeVer.gitsync}）" : ''}</td></tr>${suiteParamsRows}
    <tr><th>通过率</th><td>${rateLabel}</td></tr>
    <tr><th>测试结果</th><td style="color: ${bannerColor}; font-weight: bold;">${resultLabel}</td></tr>
    <tr><th>执行时间</th><td>${currentBuild.durationString}</td></tr>
    <tr><th>构建状态</th><td>${currentBuild.currentResult}</td></tr>
</table>
${reportFile && fileExists(reportFile) ? '<p>详细测试报告（原始 HTML 格式）请查看邮件附件 <strong>report.html</strong>。</p>' : '<p>未能生成 HTML 测试报告，请查看构建日志。</p>'}
<p>Jenkins 构建地址: <a href="${env.BUILD_URL}">${env.BUILD_URL}</a></p>
<div class="email-footer">此邮件由 Jenkins 自动发送，请勿回复。</div>
</body>
</html>"""

                        def attachPatterns = []
                        if (reportFile && fileExists(reportFile)) {
                            attachPatterns.add("reports/${BUILD_NUMBER}/engineering_*/report.html")
                            attachPatterns.add("reports/${BUILD_NUMBER}/stress_*/report.html")
                        }

                        emailext(
                            subject: "[K3.1供应商${suiteLabel}] ${params.MODEL} - ${params.SUITE} - 构建 #${BUILD_NUMBER} - ${resultLabel}${rateLabel != 'N/A' ? " (通过率 ${rateLabel})" : ''}",
                            body: emailBody,
                            to: "${params.RECIPIENTS}",
                            mimeType: 'text/html',
                            attachmentsPattern: attachPatterns.join(',')
                        )
                    }
                }
            }
        }

        stage('清理旧构建') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
cd ${params.WORK_DIR}/builds/${params.SUITE}/${params.TESTER} 2>/dev/null || exit 0
# 目录层级 <model>/<build号>/：每个模型目录内只保留最近 20 个构建
for MODEL_DIR in */ ; do
    if [ -d "\$MODEL_DIR" ]; then
        ( cd "\$MODEL_DIR" 2>/dev/null && ls -t | tail -n +21 | xargs -r rm -rf )
        rmdir "\$MODEL_DIR" 2>/dev/null || true
    fi
done
ENDSSH"""
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: "reports/${env.BUILD_NUMBER}/**", allowEmptyArchive: true, fingerprint: true
        }
        cleanup {
            cleanWs()
        }
    }
}
