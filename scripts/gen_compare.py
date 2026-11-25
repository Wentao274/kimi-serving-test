#!/usr/bin/env python
"""生成 供应商 vs 官方 双通道对比报告 + 汇总属性（供 Jenkins 邮件）。

用法：
    python scripts/gen_compare.py <out_root>

输入（取各自最新一份）：
    <out_root>/<suite>/<时间戳>/report_data.json          → 供应商侧
    <out_root>/official/<suite>/<时间戳>/report_data.json → 官方侧

产出：
    <out_root>/<model>_compare_<yyyymmddhhmmss>.html   双通道对比报告（左右两栏）
    <out_root>/compare.properties                       汇总键值（键名仅小写字母）
"""

from __future__ import annotations

import glob
import html as html_mod
import json
import os
import sys
import time
from pathlib import Path

# 功能套件模块名→中文标题（与 k31basesuite 单一数据源对齐）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "k31test" / "function-test"))
try:
    from k31basesuite.module_titles import (SUBGROUP_ORDER, case_subgroup,
                                            subgroup_tag,
                                            titles_for as _func_titles_for)
except ImportError:
    _func_titles_for = None
    SUBGROUP_ORDER, case_subgroup, subgroup_tag = [], None, None

# 当前运行套件的模块标题映射（main 中按套件设置；默认对外版口径）
_ACTIVE_TITLES: dict[str, str] = {}

_MAX_FIELD = 65536  # 单字段展示截断（完整内容见 report_data.json）

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; background: #f3f4f6; color: #111827; }
.header { background: #111827; color: #f9fafb; padding: 20px 32px; }
.header h1 { margin: 0 0 8px; font-size: 20px; }
.header .meta { font-size: 12px; color: #9ca3af; line-height: 1.7; }
.header .meta code { color: #e5e7eb; background: #374151; padding: 1px 6px; border-radius: 4px; }
.container { padding: 16px 32px 48px; }
h2 { font-size: 15px; margin: 20px 0 8px; color: #374151; }
.suite-title { font-size: 15px; font-weight: 700; margin: 22px 0 8px; color: #374151; }
.subgroup-title { font-size: 13px; font-weight: 600; margin: 12px 0 6px 14px; color: #4b5563; }
table.sum { border-collapse: collapse; background: #fff; font-size: 13px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
table.sum th, table.sum td { border: 1px solid #d8dfeb; padding: 6px 14px; text-align: left; }
table.sum th { background: #e3edfc; color: #1e3a8a; }
.lane-hd { display: flex; gap: 12px; font-size: 13px; font-weight: 700; color: #374151; padding: 10px 0 4px; }
.lane-hd span { flex: 1; }
.case { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: start; margin-bottom: 10px; }
.lane { min-width: 0; background: #fff; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.06); overflow: hidden; }
.lane .head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; }
.lane .head:hover { background: #f9fafb; }
.badge { display: inline-block; min-width: 52px; text-align: center; font-size: 11px; font-weight: 700; color: #fff; border-radius: 4px; padding: 2px 6px; flex-shrink: 0; }
.badge.passed { background: #16a34a; } .badge.failed { background: #dc2626; }
.badge.error { background: #b45309; } .badge.skipped { background: #6b7280; }
.badge.missing { background: #9ca3af; } .badge.warn { background: #d97706; }
.ttl { font-size: 12px; font-weight: 600; flex: 1; word-break: break-all; }
.time { font-size: 11px; color: #6b7280; white-space: nowrap; }
.body { display: none; border-top: 1px solid #e5e7eb; padding: 8px 12px; }
.case.open .body { display: block; }
.kv { font-size: 11px; color: #4b5563; margin-bottom: 6px; }
.kv b { color: #111827; }
table.assertions { width: 100%; border-collapse: collapse; margin: 6px 0 8px; font-size: 11px; }
table.assertions th, table.assertions td { border: 1px solid #e5e7eb; padding: 4px 6px; text-align: left; }
table.assertions th { background: #f9fafb; }
td.ok { color: #16a34a; font-weight: 700; } td.ng { color: #dc2626; font-weight: 700; }
td.warn { color: #d97706; font-weight: 700; }
details { margin: 4px 0; }
details summary { cursor: pointer; font-size: 11px; font-weight: 600; color: #374151; padding: 2px 0; user-select: none; }
pre { background: #0b1021; color: #d1e7ff; border-radius: 6px; padding: 8px 10px; font-size: 10.5px; line-height: 1.5; overflow: auto; max-height: 360px; white-space: pre-wrap; word-break: break-all; }
pre.error { background: #2d0a0a; color: #ffb4b4; }
.case.mismatch .lane.vendor_only_fail { outline: 2px solid #fecaca; }
.case.mismatch .lane.official_only_fail { outline: 2px solid #fde68a; }
.toolbar { margin: 12px 0 16px; }
.toolbar button { border: 1px solid #d1d5db; background: #fff; border-radius: 6px; padding: 5px 12px; cursor: pointer; font-size: 12px; }
.toolbar button.active { background: #111827; color: #fff; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin: 14px 0 4px; }
.stat { background: #fff; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.06); padding: 12px 14px; text-align: center; cursor: pointer; border: 2px solid transparent; }
.stat:hover { border-color: #93c5fd; }
.stat .num { font-size: 22px; font-weight: 800; }
.stat .lbl { font-size: 12px; color: #6b7280; margin-top: 2px; }
.stat.passed .num { color: #16a34a; } .stat.failed .num { color: #dc2626; }
.stat.warn .num { color: #d97706; } .stat.info .num { color: #1e3a8a; } .stat.other .num { color: #6b7280; }
"""

_JS = """
// 多选过滤：按钮可切换，多个状态取并集；「全部显示」为重置。
function _applyFilter() {
  // 收集已选状态（"全部显示"不计入，它仅作重置按钮）
  var actives = [];
  document.querySelectorAll('.toolbar button.active').forEach(b => {
    if (b.dataset.status !== 'all') actives.push(b.dataset.status);
  });
  var showAll = actives.length === 0;
  // "全部显示"按钮的高亮态 = 是否没有任何筛选
  document.querySelectorAll('.toolbar button[data-status="all"]').forEach(b =>
    b.classList.toggle('active', showAll));
  document.querySelectorAll('.case').forEach(c => {
    var st = c.dataset.status;
    var show = showAll
      || actives.includes(st)
      || (actives.includes('warn') && c.dataset.warn === '1')
      || (actives.includes('mismatch') && (st === 'vendor_only_fail' || st === 'official_only_fail'));
    c.style.display = show ? '' : 'none';
  });
}
function filterCases(status, btn) {
  // 切换该状态的选中态（保留其他已选状态，实现多选）；
  // 选择任何筛选标签时，"全部显示"自动取消选中
  if (btn && status !== 'all') {
    btn.classList.toggle('active');
    document.querySelectorAll('.toolbar button[data-status="all"]')
      .forEach(b => b.classList.remove('active'));
  } else if (btn && status === 'all') {
    document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
  }
  _applyFilter();
}
function filterByCard(status) {
  // 卡片点击与按钮一致：切换该状态选中态（多选）
  document.querySelectorAll('.toolbar button').forEach(b => {
    if (b.dataset.status === status) b.classList.toggle('active');
  });
  _applyFilter();
}
function showAll(btn) {
  document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  _applyFilter();
}
function showMismatch(btn) { filterCases('mismatch', btn); }
function toggleCase(el) { el.closest('.case').classList.toggle('open'); }
"""


def _latest(pattern: str) -> str | None:
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {r["case_id"]: r for r in d["records"]}, d["summary"], d.get("meta", {})


def _esc(x) -> str:
    return html_mod.escape(str(x))


def _pretty(obj) -> str:
    if isinstance(obj, (dict, list)):
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        text = str(obj)
    if len(text) > _MAX_FIELD:
        text = text[:_MAX_FIELD] + f"\n\n... [已截断，原始长度 {len(text)} 字符，完整内容见 report_data.json]"
    return text


def _render_assertions(rec: dict) -> str:
    rows = []
    for a in rec.get("assertions") or []:
        if a.get("soft") and not a.get("passed"):
            cls, mark = "warn", "警告"
        elif a.get("passed"):
            cls, mark = "ok", "通过"
        else:
            cls, mark = "ng", "失败"
        soft = " <small>[soft]</small>" if a.get("soft") else ""
        rows.append(f"<tr><td class='{cls}'>{mark}</td><td>{_esc(a.get('name',''))}{soft}</td>"
                    f"<td>{_esc(a.get('detail',''))}</td></tr>")
    if not rows:
        return ""
    return ("<table class='assertions'><tr><th style='width:52px'>结果</th>"
            f"<th style='width:180px'>断言</th><th>明细</th></tr>{''.join(rows)}</table>")


def _has_warn(rec: dict | None) -> bool:
    """该侧是否存在软性警告（soft 断言未通过）。"""
    return bool(rec) and any(a.get("soft") and not a.get("passed")
                             for a in rec.get("assertions") or [])


def _render_lane(rec: dict | None, side: str, status: str) -> str:
    if rec is None:
        return f"<div class='lane {side}'><div class='head'><span class='badge missing'>N/A</span><span class='ttl'>未执行</span></div></div>"
    outcome = rec.get("outcome", "passed")
    bits = []
    if rec.get("latency_s") is not None:
        bits.append(f"总耗时 {rec['latency_s']}s")
    if rec.get("ttft_s") is not None:
        bits.append(f"TTFT {rec['ttft_s']}s")
    usage_bits = []
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in (rec.get("usage") or {}):
            usage_bits.append(f"{k}={rec['usage'][k]}")
    if rec.get("finish_reason"):
        usage_bits.append(f"finish={rec['finish_reason']}")

    warn_assertions = [a for a in (rec.get("assertions") or []) if a.get("soft") and not a.get("passed")]
    warn_badge = (f"<span class='badge warn' title='含 {len(warn_assertions)} 条软性警告'>"
                  f"⚠ {len(warn_assertions)}</span>") if warn_assertions else ""

    parts = [
        f"<div class='lane {side}'>",
        f"<div class='head' onclick='toggleCase(this)'>",
        f"<span class='badge {outcome}'>{outcome.upper()}</span>",
        warn_badge,
        f"<span class='ttl'>{_esc(rec.get('title') or rec.get('case_id'))}</span>",
        f"<span class='time'>{_esc(' | '.join(bits))}</span>",
        "</div><div class='body'>",
    ]
    parts.append(f"<div class='kv'><b>用例：</b>{_esc(rec.get('case_id'))}</div>")
    if rec.get("description"):
        parts.append(f"<div class='kv'><b>说明：</b>{_esc(rec['description'])}</div>")
    if usage_bits:
        parts.append(f"<div class='kv'><b>用量：</b>{_esc(', '.join(usage_bits))}</div>")
    parts.append(_render_assertions(rec))
    if rec.get("error") and outcome in ("failed", "error", "skipped"):
        label = "跳过原因" if outcome == "skipped" else "错误信息"
        parts.append(f"<details open><summary>{label}</summary><pre class='error'>{_esc(_pretty(rec['error']))}</pre></details>")
    if rec.get("extra"):
        parts.append(f"<details><summary>附加信息</summary><pre>{_esc(_pretty(rec['extra']))}</pre></details>")
    # 复现命令 (curl)：与单侧报告一致，左右两栏各自展示
    curl_cmd = (rec.get("request") or {}).get("curl") if isinstance(rec.get("request"), dict) else None
    if curl_cmd:
        parts.append(f"<details><summary>复现命令 (curl)</summary><pre>{_esc(curl_cmd)}</pre></details>")
    if rec.get("request") is not None:
        parts.append(f"<details><summary>请求 (Request)</summary><pre>{_esc(_pretty(rec['request']))}</pre></details>")
    if rec.get("response") is not None:
        parts.append(f"<details><summary>响应 (Response)</summary><pre>{_esc(_pretty(rec['response']))}</pre></details>")
    parts.append("</div></div>")
    return "".join(parts)


# 套件模块名 → 中文标题（用于套件分组头展示）
MODULE_TITLES = {
    "test_00_smoke_connectivity": "前置冒烟",
    "test_01_protocol_format": "协议格式",
    "test_01_thinking_mode": "Thinking Mode",
    "test_02_usage_fields": "usage 字段",
    "test_02_param_defaults": "参数默认值",
    "test_03_thinking_mode": "thinking 模式",
    "test_03_max_tokens_default": "max_tokens 默认值",
    "test_04_sampling_params": "采样参数",
    "test_04_no_system_prompt": "System Prompt",
    "test_05_streaming_metering": "流式与计量",
    "test_05_image_cases": "图片输入用例",
    "test_06_structured_output": "结构化输出",
    "test_06_trace_id": "Trace ID",
    "test_07_tool_calls": "工具调用",
    "test_07_token_statistics": "Token 统计分类",
    "test_08_error_codes": "错误码",
    "test_08_provider_deploy_id": "X-Msh-ProviderDeployId",
    "test_09_observability": "可观测性",
    "test_09_streaming_output_spec": "Streaming Output Spec",
    "test_10_timeout": "超时时间",
    "test_10_new_model_spec": "New Model Spec",
    "test_11_thinking_effort": "Thinking effort",
    "test_12_openclaw_cases": "OpenClaw 用例",
    "test_13_preserve_thinking": "Preserve thinking",
}


def _suite_title(suite: str) -> str:
    """模块名 → 中文标题（按当前套件口径映射，未命中回退原名）。"""
    name = suite.rsplit(".", 1)[-1]
    return _ACTIVE_TITLES.get(name) or MODULE_TITLES.get(name, name)


def _rate(passed: int, total: int, skipped: int) -> float:
    """通过率 = 通过数 /（总用例 - 跳过数）"""
    denom = total - skipped
    return round(passed / denom * 100, 2) if denom > 0 else 0.0


def _bucket(outcome: str) -> str:
    """把 outcome 归为五桶：passed / failed / skipped / other（missing）。"""
    if outcome == "passed":
        return "passed"
    if outcome in ("failed", "error"):
        return "failed"
    if outcome == "skipped":
        return "skipped"
    return "other"


def render_dual(vrec, orec, vsum, osum, vmeta, ometa, model: str, stamp: str) -> str:
    cats = {"both_pass": 0, "vendor_only_fail": 0, "official_only_fail": 0,
            "both_fail": 0, "vendor_fail_official_skip": 0,
            "official_fail_vendor_skip": 0, "other": 0}
    suites: dict[str, list[tuple[str, dict | None, dict | None, str]]] = {}
    for cid in sorted(set(vrec) | set(orec)):
        v, o = vrec.get(cid), orec.get(cid)
        vb = _bucket(v["outcome"]) if v else "other"
        ob = _bucket(o["outcome"]) if o else "other"
        if vb == "passed" and ob == "passed":
            status = "both_pass"
        elif vb == "failed" and ob == "passed":
            status = "vendor_only_fail"
        elif vb == "passed" and ob == "failed":
            status = "official_only_fail"
        elif vb == "failed" and ob == "failed":
            status = "both_fail"
        elif vb == "failed" and ob == "skipped":
            status = "vendor_fail_official_skip"
        elif vb == "skipped" and ob == "failed":
            status = "official_fail_vendor_skip"
        else:
            status = "other"
        cats[status] += 1
        suite = (v or o).get("suite", "unknown")
        # 分组键 = 分类标题（映射后），同分类的多个模块并入同一节点
        suites.setdefault(_suite_title(suite), []).append((cid, v, o, status))

    vendor_rate = _rate(vsum["passed"], vsum["total"], vsum.get("skipped", 0))
    official_rate = _rate(osum["passed"], osum["total"], osum.get("skipped", 0))

    suite_html = []
    n_warn_cases = 0

    def _emit_case(cid, v, o, status, sg_tag: str) -> None:
        nonlocal n_warn_cases
        cls = "case" + (" mismatch" if status in ("vendor_only_fail", "official_only_fail") else "")
        v_cls = "vendor_only_fail" if status == "vendor_only_fail" else ("official_only_fail" if status == "official_only_fail" else "")
        o_cls = "official_only_fail" if status == "official_only_fail" else ("vendor_only_fail" if status == "vendor_only_fail" else "")
        has_warn = _has_warn(v) or _has_warn(o)
        if has_warn:
            n_warn_cases += 1
        if sg_tag and v:
            v = {**v, "title": f"[{sg_tag}] {v.get('title') or cid}"}
        if sg_tag and o:
            o = {**o, "title": f"[{sg_tag}] {o.get('title') or cid}"}
        suite_html.append(
            f"<div class='{cls}' data-status='{status}' data-warn='{1 if has_warn else 0}'>"
            f"{_render_lane(v, 'lane vendor ' + v_cls, status)}"
            f"{_render_lane(o, 'lane official ' + o_cls, status)}"
            f"</div>"
        )

    for suite, cases in suites.items():
        np_ = sum(1 for _, v, _, _ in cases if v and v["outcome"] == "passed")
        no_ = sum(1 for _, _, o, _ in cases if o and o["outcome"] == "passed")
        suite_html.append(f"<div class='suite-title'>{_esc(suite)} "
                          f"<small style='color:#6b7280'>({len(cases)} 用例 | 供应商 {np_} 通过 | 官方 {no_} 通过)</small></div>")
        # 参数子组（仅"采样与输出预算"分类内的模块有子组映射）
        subgroups: dict[str | None, list] = {}
        for cid, v, o, status in cases:
            sg = case_subgroup((v or o).get("suite", "") if (v or o) else "", cid) if case_subgroup else None
            subgroups.setdefault(sg, []).append((cid, v, o, status))
        if any(k is not None for k in subgroups):
            ordered = [k for k in SUBGROUP_ORDER if k in subgroups]
            ordered += [None] if None in subgroups else []
            for sg in ordered:
                rs = subgroups[sg]
                n_v = sum(1 for _, v, _, _ in rs if v and v["outcome"] == "passed")
                n_o = sum(1 for _, _, o, _ in rs if o and o["outcome"] == "passed")
                if sg is not None:
                    suite_html.append(
                        f"<div class='subgroup-title'>└ {_esc(sg)} "
                        f"<small style='color:#6b7280'>(供应商 {n_v}/{len(rs)} | 官方 {n_o}/{len(rs)})</small></div>")
                for cid, v, o, status in rs:
                    _emit_case(cid, v, o, status, subgroup_tag(sg) if sg is not None else "")
        else:
            for cid, v, o, status in cases:
                _emit_case(cid, v, o, status, "")

    meta_rows = " &nbsp; ".join([
        f"<span>模型: <code>{_esc(model)}</code></span>",
        f"<span>供应商: <code>{_esc(vmeta.get('Endpoint', '?'))}</code></span>",
        f"<span>官方: <code>{_esc(ometa.get('Endpoint', '?'))}</code></span>",
        f"<span>生成时间: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code></span>",
    ])

    total_cases = sum(cats.values())
    stat_cards = "".join(
        f"<div class='stat {cls}' onclick=\"filterByCard('{st}')\" title='点击过滤'><div class='num'>{num}</div><div class='lbl'>{lbl}</div></div>"
        for cls, num, lbl, st in [
            ("info", total_cases, "总用例", "all"),
            ("info", f"{vendor_rate}%", "供应商通过率", "all"),
            ("info", f"{official_rate}%", "官方通过率", "all"),
            ("passed", cats['both_pass'], "双均通过", "both_pass"),
            ("failed", cats['vendor_only_fail'], "仅供应商失败", "vendor_only_fail"),
            ("warn", cats['official_only_fail'], "仅官方失败", "official_only_fail"),
            ("failed", cats['both_fail'], "双均失败", "both_fail"),
            ("failed", cats['vendor_fail_official_skip'], "供应商失败(官方跳过)", "vendor_fail_official_skip"),
            ("warn", cats['official_fail_vendor_skip'], "官方失败(供应商跳过)", "official_fail_vendor_skip"),
            ("other", cats['other'], "其他/未执行", "other"),
            ("warn", n_warn_cases, "软性警告", "warn"),
        ]
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{_esc(model)} 供应商 vs 官方 对比报告</title><style>{_CSS}</style></head>
<body>
<div class="header"><h1>{_esc(model)} — 供应商 vs 官方 对比报告</h1><div class="meta">{meta_rows}</div></div>
<div class="container">
<div class="summary">{stat_cards}</div>
<h2>供应商 vs 官方 对比汇总</h2>
<table class="sum">
<tr><th></th><th>总用例</th><th>通过</th><th>失败</th><th>跳过</th><th>通过率</th></tr>
<tr><th>供应商</th><td>{vsum['total']}</td><td>{vsum['passed']}</td><td>{vsum['failed']}</td><td>{vsum['skipped']}</td><td>{vendor_rate}%</td></tr>
<tr><th>官方</th><td>{osum['total']}</td><td>{osum['passed']}</td><td>{osum['failed']}</td><td>{osum['skipped']}</td><td>{official_rate}%</td></tr>
</table>
<p style="font-size:12px;color:#6b7280;margin:6px 0 0;">注：通过率 = 通过数 /（总数 - 跳过数）</p>
<div class="toolbar">
  <button class="active" data-status="all" onclick="showAll(this)">全部显示</button>
  <button data-status="both_pass" onclick="filterCases('both_pass', this)">双均通过</button>
  <button data-status="vendor_only_fail" onclick="filterCases('vendor_only_fail', this)">仅供应商失败</button>
  <button data-status="official_only_fail" onclick="filterCases('official_only_fail', this)">仅官方失败</button>
  <button data-status="both_fail" onclick="filterCases('both_fail', this)">双均失败</button>
  <button data-status="vendor_fail_official_skip" onclick="filterCases('vendor_fail_official_skip', this)">供应商失败(官方跳过)</button>
  <button data-status="official_fail_vendor_skip" onclick="filterCases('official_fail_vendor_skip', this)">官方失败(供应商跳过)</button>
  <button data-status="other" onclick="filterCases('other', this)">其他/未执行</button>
  <button data-status="warn" onclick="filterCases('warn', this)">软性警告</button>
  <button data-status="mismatch" onclick="showMismatch(this)">仅看不一致</button>
</div>
<div class="lane-hd"><span>◀ 供应商（左）</span><span>▶ 官方（右）</span></div>
{''.join(suite_html)}
</div>
<script>{_JS}</script>
</body></html>"""


def main() -> int:
    global _ACTIVE_TITLES
    out_root = sys.argv[1]
    suite = sys.argv[2] if len(sys.argv) > 2 else "engineering"
    if _func_titles_for is not None:
        _ACTIVE_TITLES = _func_titles_for(suite)
    vendor_path = _latest(os.path.join(out_root, suite, "*", "report_data.json"))
    official_path = _latest(os.path.join(out_root, "official", suite, "*", "report_data.json"))
    if not vendor_path or not official_path:
        print(f"[gen_compare] 缺少一侧报告，跳过对比（vendor={vendor_path}, official={official_path}）")
        return 0

    vrec, vsum, vmeta = _load(vendor_path)
    orec, osum, ometa = _load(official_path)
    model = vmeta.get("模型") or ometa.get("模型") or "model"
    safe_model = "".join(c if (c.isalnum() or c in "._-") else "_" for c in model)
    stamp = time.strftime("%Y%m%d%H%M%S")

    cats = {"bothpass": 0, "vendoronlyfail": 0, "officialonlyfail": 0,
            "bothfail": 0, "vendorfailofficialskip": 0,
            "officialfailvendorskip": 0, "other": 0}
    for cid in set(vrec) | set(orec):
        v, o = vrec.get(cid), orec.get(cid)
        vb = _bucket(v["outcome"]) if v else "other"
        ob = _bucket(o["outcome"]) if o else "other"
        if vb == "passed" and ob == "passed":
            cats["bothpass"] += 1
        elif vb == "failed" and ob == "passed":
            cats["vendoronlyfail"] += 1
        elif vb == "passed" and ob == "failed":
            cats["officialonlyfail"] += 1
        elif vb == "failed" and ob == "failed":
            cats["bothfail"] += 1
        elif vb == "failed" and ob == "skipped":
            cats["vendorfailofficialskip"] += 1
        elif vb == "skipped" and ob == "failed":
            cats["officialfailvendorskip"] += 1
        else:
            cats["other"] += 1

    # 双通道对比报告：<model>_compare_<stamp>.html
    page = render_dual(vrec, orec, vsum, osum, vmeta, ometa, safe_model, stamp)
    html_path = os.path.join(out_root, f"{safe_model}_compare_{stamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)

    props = {
        "vendortotal": vsum["total"], "vendorpassed": vsum["passed"],
        "vendorrate": round(vsum["passed"] / max(vsum["total"], 1) * 100, 2),
        "officialtotal": osum["total"], "officialpassed": osum["passed"],
        "officialrate": round(osum["passed"] / max(osum["total"], 1) * 100, 2),
        **cats,
        "comparehtml": os.path.basename(html_path),
    }
    with open(os.path.join(out_root, "compare.properties"), "w", encoding="utf-8") as f:
        for k, v in props.items():
            f.write(f"{k}={v}\n")
    print(f"[gen_compare] {html_path}")
    print(f"[gen_compare] {props}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
