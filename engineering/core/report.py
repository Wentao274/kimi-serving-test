"""HTML 报告渲染：单文件、可折叠、可过滤，包含每个用例的请求/响应与断言明细。"""

from __future__ import annotations

import html
import json
from typing import Any

from .recorder import Collector, CaseRecord

# HTML 中单个字段的最大展示字符数（完整内容见 report_data.json）
_MAX_HTML_FIELD = 65536

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
       margin: 0; background: #f3f4f6; color: #111827; }
.header { background: #111827; color: #f9fafb; padding: 20px 32px; }
.header h1 { margin: 0 0 8px; font-size: 20px; }
.header .meta { font-size: 12px; color: #9ca3af; line-height: 1.7; }
.header .meta code { color: #e5e7eb; background: #374151; padding: 1px 6px; border-radius: 4px; }
.container { padding: 16px 32px 48px; }
.summary { display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
.stat { background: #fff; border-radius: 8px; padding: 12px 20px; min-width: 110px;
        box-shadow: 0 1px 2px rgba(0,0,0,.06); text-align: center; }
.stat .num { font-size: 24px; font-weight: 700; }
.stat .lbl { font-size: 12px; color: #6b7280; margin-top: 2px; }
.stat.passed .num { color: #16a34a; } .stat.failed .num { color: #dc2626; }
.stat.error .num { color: #b45309; } .stat.skipped .num { color: #6b7280; }
.stat.soft .num { color: #d97706; }
.toolbar { display: flex; gap: 8px; align-items: center; margin: 12px 0 16px; flex-wrap: wrap; }
.toolbar button { border: 1px solid #d1d5db; background: #fff; border-radius: 6px;
                  padding: 6px 14px; cursor: pointer; font-size: 13px; }
.toolbar button.active { background: #111827; color: #fff; border-color: #111827; }
.toolbar input { flex: 1; min-width: 220px; padding: 7px 12px; border: 1px solid #d1d5db;
                 border-radius: 6px; font-size: 13px; }
.suite-title { font-size: 15px; font-weight: 700; margin: 22px 0 8px; color: #374151; }
.case { background: #fff; border-radius: 8px; margin-bottom: 10px;
        box-shadow: 0 1px 2px rgba(0,0,0,.06); overflow: hidden; }
.case-head { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; }
.case-head:hover { background: #f9fafb; }
.badge { display: inline-block; min-width: 56px; text-align: center; font-size: 11px;
         font-weight: 700; color: #fff; border-radius: 4px; padding: 2px 8px; flex-shrink: 0; }
.badge.passed { background: #16a34a; } .badge.failed { background: #dc2626; }
.badge.error { background: #b45309; } .badge.skipped { background: #6b7280; }
.badge.warn { background: #d97706; min-width: 40px; }
.stat { cursor: pointer; }
.stat:hover { outline: 2px solid #9ca3af; }
.stat.soft:hover { outline: 2px solid #d97706; }
.case-title { font-size: 13px; font-weight: 600; flex: 1; word-break: break-all; }
.case-time { font-size: 11px; color: #6b7280; white-space: nowrap; }
.case-body { display: none; border-top: 1px solid #e5e7eb; padding: 12px 16px; }
.case.open .case-body { display: block; }
.kv { font-size: 12px; color: #4b5563; margin-bottom: 8px; }
.kv b { color: #111827; }
table.assertions { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 12px; }
table.assertions th, table.assertions td { border: 1px solid #e5e7eb; padding: 5px 8px; text-align: left; }
table.assertions th { background: #f9fafb; }
td.ok { color: #16a34a; font-weight: 700; } td.ng { color: #dc2626; font-weight: 700; }
td.warn { color: #d97706; font-weight: 700; }
details { margin: 6px 0; }
details summary { cursor: pointer; font-size: 12px; font-weight: 600; color: #374151;
                  padding: 4px 0; user-select: none; }
pre { background: #0b1021; color: #d1e7ff; border-radius: 6px; padding: 10px 12px;
      font-size: 11px; line-height: 1.55; overflow: auto; max-height: 480px;
      white-space: pre-wrap; word-break: break-all; }
pre.error { background: #2d0a0a; color: #ffb4b4; }
"""

_JS = """
function filterCases(status, btn) {
  document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.case').forEach(c => {
    const matchStatus = (status === 'all')
      ? true
      : (status === 'warn' ? c.classList.contains('has-warn') : c.dataset.status === status);
    const matchQuery = (!q || c.dataset.search.includes(q));
    c.style.display = (matchStatus && matchQuery) ? '' : 'none';
  });
}
function filterWarn() {
  const btn = document.getElementById('btn-warn');
  if (btn) filterCases('warn', btn);
}
function filterByCard(status) {
  const btn = document.querySelector('.toolbar button[data-status="' + status + '"]');
  if (btn) filterCases(status, btn);
}
function searchCases() {
  const active = document.querySelector('.toolbar button.active');
  filterCases(active ? active.dataset.status : 'all', active || document.querySelector('.toolbar button'));
}
function toggleCase(el) { el.closest('.case').classList.toggle('open'); }
function expandAll(open) {
  document.querySelectorAll('.case').forEach(c => c.classList.toggle('open', open));
}
"""


def _esc(s: Any) -> str:
    return html.escape(str(s))


def _pretty(obj: Any) -> str:
    if isinstance(obj, (dict, list)):
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        text = str(obj)
    if len(text) > _MAX_HTML_FIELD:
        text = text[:_MAX_HTML_FIELD] + (
            f"\n\n... [已截断，原始长度 {len(text)} 字符，完整内容见 report_data.json]"
        )
    return text


def _render_assertions(rec: CaseRecord) -> str:
    if not rec.assertions:
        return ""
    rows = []
    for a in rec.assertions:
        if a.soft and not a.passed:
            cls, mark = "warn", "警告"
        elif a.passed:
            cls, mark = "ok", "通过"
        else:
            cls, mark = "ng", "失败"
        soft_tag = " <small>[soft]</small>" if a.soft else ""
        rows.append(
            f"<tr><td class='{cls}'>{mark}</td><td>{_esc(a.name)}{soft_tag}</td>"
            f"<td>{_esc(a.detail)}</td></tr>"
        )
    return (
        "<table class='assertions'><tr><th style='width:56px'>结果</th>"
        f"<th style='width:340px'>断言</th><th>明细</th></tr>{''.join(rows)}</table>"
    )


def _render_case(rec: CaseRecord) -> str:
    timing = []
    if rec.latency_s is not None:
        timing.append(f"总耗时 {rec.latency_s}s")
    if rec.ttft_s is not None:
        timing.append(f"TTFT {rec.ttft_s}s")
    usage_bits = []
    for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"):
        if k in (rec.usage or {}):
            usage_bits.append(f"{k}={rec.usage[k]}")
    if rec.finish_reason:
        usage_bits.append(f"finish={rec.finish_reason}")

    warn_assertions = [a for a in rec.assertions if a.soft and not a.passed]
    has_warn = bool(warn_assertions)
    case_cls = "case" + (" has-warn" if has_warn else "")
    warn_badge = (f"<span class='badge warn' title='含 {len(warn_assertions)} 条软性警告'>"
                  f"⚠ {len(warn_assertions)}</span>") if has_warn else ""

    parts = [
        f"<div class='{case_cls}' data-status='{rec.outcome}' "
        f"data-search='{_esc((rec.case_id + ' ' + rec.title).lower())}'>",
        f"<div class='case-head' onclick='toggleCase(this)'>",
        f"<span class='badge {rec.outcome}'>{rec.outcome.upper()}</span>",
        warn_badge,
        f"<span class='case-title'>{_esc(rec.title)}</span>",
        f"<span class='case-time'>{_esc(' | '.join(timing))}</span>",
        "</div><div class='case-body'>",
    ]
    if rec.description:
        parts.append(f"<div class='kv'><b>说明：</b>{_esc(rec.description)}</div>")
    parts.append(f"<div class='kv'><b>用例：</b>{_esc(rec.case_id)}</div>")
    if usage_bits:
        parts.append(f"<div class='kv'><b>用量：</b>{_esc(', '.join(usage_bits))}</div>")
    parts.append(_render_assertions(rec))
    if rec.error and rec.outcome in ("failed", "error", "skipped"):
        label = "跳过原因" if rec.outcome == "skipped" else "错误信息"
        parts.append(
            f"<details open><summary>{label}</summary>"
            f"<pre class='error'>{_esc(_pretty(rec.error))}</pre></details>"
        )
    if rec.extra:
        parts.append(
            "<details><summary>附加信息</summary>"
            f"<pre>{_esc(_pretty(rec.extra))}</pre></details>"
        )
    if rec.request is not None:
        curl_cmd = rec.request.get("curl") if isinstance(rec.request, dict) else None
        if curl_cmd:
            parts.append(
                "<details><summary>复现命令 (curl)</summary>"
                f"<pre>{_esc(curl_cmd)}</pre></details>"
            )
        parts.append(
            "<details><summary>请求 (Request)</summary>"
            f"<pre>{_esc(_pretty(rec.request))}</pre></details>"
        )
    if rec.response is not None:
        parts.append(
            "<details><summary>响应 (Response)</summary>"
            f"<pre>{_esc(_pretty(rec.response))}</pre></details>"
        )
    parts.append("</div></div>")
    return "".join(parts)


def render_html(collector: Collector, meta: dict[str, Any],
                module_titles: dict[str, str] | None = None) -> str:
    summary = collector.summary()
    suites: dict[str, list[CaseRecord]] = {}
    for rec in collector.records:
        suites.setdefault(rec.suite, []).append(rec)

    warn_cases = sum(
        1 for r in collector.records
        if any(a.soft and not a.passed for a in r.assertions)
    )

    stat_cards = "".join(
        f"<div class='stat {cls}'{extra}><div class='num'>{num}</div><div class='lbl'>{lbl}</div></div>"
        for cls, num, lbl, extra in [
            ("", summary.get("total", 0), "总用例",
             " onclick='filterByCard(\"all\")' title='点击显示全部'"),
            ("passed", summary.get("passed", 0), "通过",
             " onclick='filterByCard(\"passed\")' title='点击筛选通过用例'"),
            ("failed", summary.get("failed", 0), "失败",
             " onclick='filterByCard(\"failed\")' title='点击筛选失败用例'"),
            ("error", summary.get("error", 0), "错误",
             " onclick='filterByCard(\"error\")' title='点击筛选错误用例'"),
            ("skipped", summary.get("skipped", 0), "跳过",
             " onclick='filterByCard(\"skipped\")' title='点击筛选跳过用例'"),
            ("soft", summary.get("soft_warnings", 0), "软性警告",
             " onclick='filterWarn()' title='点击筛选含警告用例'"),
        ]
    )

    suite_blocks = []
    for suite, records in suites.items():
        n_pass = sum(1 for r in records if r.outcome == "passed")
        short = suite.rsplit(".", 1)[-1]
        disp = (module_titles or {}).get(short, suite)
        block = [
            f"<div class='suite-title'>{_esc(disp)} "
            f"<small style='color:#6b7280'>({n_pass}/{len(records)} 通过)</small></div>"
        ]
        block.extend(_render_case(r) for r in records)
        suite_blocks.append("".join(block))

    meta_rows = " &nbsp; ".join(
        f"<span>{_esc(k)}: <code>{_esc(v)}</code></span>" for k, v in meta.items()
    )

    _model = str(meta.get("模型") or meta.get("model") or "?")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{_esc(_model)} - 工程能力测试报告</title>
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <h1>{_esc(_model)} - 工程能力测试报告</h1>
  <div class="meta">{meta_rows}</div>
</div>
<div class="container">
  <div class="summary">{stat_cards}</div>
  <div class="toolbar">
    <button class="active" data-status="all" onclick="filterCases('all', this)">全部</button>
    <button data-status="passed" onclick="filterCases('passed', this)">通过</button>
    <button data-status="failed" onclick="filterCases('failed', this)">失败</button>
    <button data-status="error" onclick="filterCases('error', this)">错误</button>
    <button data-status="skipped" onclick="filterCases('skipped', this)">跳过</button>
    <button id="btn-warn" data-status="warn" onclick="filterCases('warn', this)">警告 ({warn_cases})</button>
    <input id="search" type="text" placeholder="搜索用例名 / 标题..." oninput="searchCases()">
    <button onclick="expandAll(true)">全部展开</button>
    <button onclick="expandAll(false)">全部收起</button>
  </div>
  {''.join(suite_blocks)}
</div>
<script>{_JS}</script>
</body>
</html>"""
