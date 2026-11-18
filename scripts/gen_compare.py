#!/usr/bin/env python
"""生成 供应商 vs 官方 双通道对比报告 + 汇总属性（供 Jenkins 邮件）。

用法：
    python scripts/gen_compare.py <out_root>

输入（取各自最新一份）：
    <out_root>/engineering_*/report_data.json          → 供应商侧
    <out_root>/official/engineering_*/report_data.json → 官方侧

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
table.sum { border-collapse: collapse; background: #fff; font-size: 13px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
table.sum th, table.sum td { border: 1px solid #d8dfeb; padding: 6px 14px; text-align: left; }
table.sum th { background: #e3edfc; color: #1e3a8a; }
.lane-hd { display: flex; gap: 12px; font-size: 13px; font-weight: 700; color: #374151; padding: 10px 0 4px; }
.lane-hd span { flex: 1; }
.case { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 10px; }
.lane { flex: 1; min-width: 0; background: #fff; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.06); overflow: hidden; }
.lane .head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; }
.lane .head:hover { background: #f9fafb; }
.badge { display: inline-block; min-width: 52px; text-align: center; font-size: 11px; font-weight: 700; color: #fff; border-radius: 4px; padding: 2px 6px; flex-shrink: 0; }
.badge.passed { background: #16a34a; } .badge.failed { background: #dc2626; }
.badge.error { background: #b45309; } .badge.skipped { background: #6b7280; }
.badge.missing { background: #9ca3af; }
.ttl { font-size: 12px; font-weight: 600; flex: 1; word-break: break-all; }
.time { font-size: 11px; color: #6b7280; white-space: nowrap; }
.body { display: none; border-top: 1px solid #e5e7eb; padding: 8px 12px; }
.lane.open .body { display: block; }
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
"""

_JS = """
function showAll(btn) { _filter('all', btn); }
function showMismatch(btn) { _filter('mismatch', btn); }
function _filter(mode, btn) {
  document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.case').forEach(c => {
    c.style.display = (mode === 'all' || c.classList.contains('mismatch')) ? '' : 'none';
  });
}
function toggleLane(el) { el.closest('.lane').classList.toggle('open'); }
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

    parts = [
        f"<div class='lane {side}'>",
        f"<div class='head' onclick='toggleLane(this)'>",
        f"<span class='badge {outcome}'>{outcome.upper()}</span>",
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


def render_dual(vrec, orec, vsum, osum, vmeta, ometa, model: str, stamp: str) -> str:
    cats = {"both_pass": 0, "vendor_only_fail": 0, "official_only_fail": 0, "both_fail": 0, "other": 0}
    suites: dict[str, list[tuple[str, dict | None, dict | None, str]]] = {}
    for cid in sorted(set(vrec) | set(orec)):
        v, o = vrec.get(cid), orec.get(cid)
        vo = v["outcome"] if v else "missing"
        oo = o["outcome"] if o else "missing"
        if vo == "passed" and oo == "passed":
            status = "both_pass"
        elif vo != "passed" and oo == "passed":
            status = "vendor_only_fail"
        elif vo == "passed" and oo != "passed":
            status = "official_only_fail"
        elif vo != "passed" and oo != "passed":
            status = "both_fail"
        else:
            status = "other"
        cats[status] += 1
        suite = (v or o).get("suite", "unknown")
        suites.setdefault(suite, []).append((cid, v, o, status))

    vendor_rate = round(vsum["passed"] / max(vsum["total"], 1) * 100, 2)
    official_rate = round(osum["passed"] / max(osum["total"], 1) * 100, 2)

    suite_html = []
    for suite, cases in suites.items():
        np_ = sum(1 for _, v, _, _ in cases if v and v["outcome"] == "passed")
        no_ = sum(1 for _, _, o, _ in cases if o and o["outcome"] == "passed")
        suite_html.append(f"<h2>{_esc(suite)} <small style='color:#6b7280'>(供应商 {np_}/{len(cases)} | 官方 {no_}/{len(cases)})</small></h2>")
        for cid, v, o, status in cases:
            cls = "case" + (" mismatch" if status in ("vendor_only_fail", "official_only_fail") else "")
            v_cls = "vendor_only_fail" if status == "vendor_only_fail" else ("official_only_fail" if status == "official_only_fail" else "")
            o_cls = "official_only_fail" if status == "official_only_fail" else ("vendor_only_fail" if status == "vendor_only_fail" else "")
            suite_html.append(
                f"<div class='{cls}'>"
                f"{_render_lane(v, 'lane vendor ' + v_cls, status)}"
                f"{_render_lane(o, 'lane official ' + o_cls, status)}"
                f"</div>"
            )

    meta_rows = " &nbsp; ".join([
        f"<span>模型: <code>{_esc(model)}</code></span>",
        f"<span>供应商: <code>{_esc(vmeta.get('Endpoint', '?'))}</code></span>",
        f"<span>官方: <code>{_esc(ometa.get('Endpoint', '?'))}</code></span>",
        f"<span>生成时间: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code></span>",
    ])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{_esc(model)} 供应商 vs 官方 对比报告</title><style>{_CSS}</style></head>
<body>
<div class="header"><h1>{_esc(model)} — 供应商 vs 官方 对比报告</h1><div class="meta">{meta_rows}</div></div>
<div class="container">
<h2>供应商 vs 官方 对比汇总</h2>
<table class="sum">
<tr><th></th><th>总用例</th><th>通过</th><th>失败</th><th>跳过</th><th>通过率</th></tr>
<tr><th>供应商</th><td>{vsum['total']}</td><td>{vsum['passed']}</td><td>{vsum['failed']}</td><td>{vsum['skipped']}</td><td>{vendor_rate}%</td></tr>
<tr><th>官方</th><td>{osum['total']}</td><td>{osum['passed']}</td><td>{osum['failed']}</td><td>{osum['skipped']}</td><td>{official_rate}%</td></tr>
<tr><th>双边均通过</th><td colspan="5">{cats['both_pass']}</td></tr>
<tr><th>仅供应商失败</th><td colspan="5" style="color:#dc2626">{cats['vendor_only_fail']}</td></tr>
<tr><th>仅官方失败</th><td colspan="5" style="color:#b45309">{cats['official_only_fail']}</td></tr>
<tr><th>双边均失败</th><td colspan="5">{cats['both_fail']}</td></tr>
</table>
<div class="toolbar">
  <button class="active" onclick="showAll(this)">全部用例</button>
  <button onclick="showMismatch(this)">仅看不一致</button>
</div>
<div class="lane-hd"><span>▼ 供应商（左）</span><span>▼ 官方（右）</span></div>
{''.join(suite_html)}
</div>
<script>{_JS}</script>
</body></html>"""


def main() -> int:
    out_root = sys.argv[1]
    vendor_path = _latest(os.path.join(out_root, "engineering_*", "report_data.json"))
    official_path = _latest(os.path.join(out_root, "official", "engineering_*", "report_data.json"))
    if not vendor_path or not official_path:
        print(f"[gen_compare] 缺少一侧报告，跳过对比（vendor={vendor_path}, official={official_path}）")
        return 0

    vrec, vsum, vmeta = _load(vendor_path)
    orec, osum, ometa = _load(official_path)
    model = vmeta.get("模型") or ometa.get("模型") or "model"
    safe_model = "".join(c if (c.isalnum() or c in "._-") else "_" for c in model)
    stamp = time.strftime("%Y%m%d%H%M%S")

    cats = {"bothpass": 0, "vendoronlyfail": 0, "officialonlyfail": 0, "bothfail": 0}
    for cid in set(vrec) | set(orec):
        v, o = vrec.get(cid), orec.get(cid)
        vo = v["outcome"] if v else "missing"
        oo = o["outcome"] if o else "missing"
        if vo == "passed" and oo == "passed":
            cats["bothpass"] += 1
        elif vo != "passed" and oo == "passed":
            cats["vendoronlyfail"] += 1
        elif vo == "passed" and oo != "passed":
            cats["officialonlyfail"] += 1
        elif vo != "passed" and oo != "passed":
            cats["bothfail"] += 1

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
