"""压力测试报告：单文件 HTML（判定矩阵 + 阶段时间线 + 窗口明细 + 质量事故 + SVG 曲线）。"""

from __future__ import annotations

import html
import json
import time
from typing import Any

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
       margin: 0; background: #f3f4f6; color: #111827; }
.header { background: #111827; color: #f9fafb; padding: 20px 32px; }
.header h1 { margin: 0 0 8px; font-size: 20px; }
.header .meta { font-size: 12px; color: #9ca3af; line-height: 1.7; }
.header .meta code { color: #e5e7eb; background: #374151; padding: 1px 6px; border-radius: 4px; }
.container { padding: 16px 32px 48px; }
h2 { font-size: 15px; margin: 24px 0 8px; color: #374151; }
.summary { display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
.stat { background: #fff; border-radius: 8px; padding: 12px 20px; min-width: 120px;
        box-shadow: 0 1px 2px rgba(0,0,0,.06); text-align: center; }
.stat .num { font-size: 22px; font-weight: 700; }
.stat .lbl { font-size: 12px; color: #6b7280; margin-top: 2px; }
.stat.pass .num { color: #16a34a; } .stat.fail .num { color: #dc2626; }
table { width: 100%; border-collapse: collapse; background: #fff; font-size: 12px;
        border-radius: 8px; overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; }
th { background: #f9fafb; }
td.ok { color: #16a34a; font-weight: 700; }
td.ng { color: #dc2626; font-weight: 700; }
td.na { color: #6b7280; font-weight: 700; }
.scroll { overflow-x: auto; }
.badge { display: inline-block; font-size: 11px; font-weight: 700; color: #fff;
         border-radius: 4px; padding: 2px 8px; }
.badge.pass { background: #16a34a; } .badge.fail { background: #dc2626; }
.badge.na { background: #6b7280; }
pre { background: #0b1021; color: #d1e7ff; border-radius: 6px; padding: 10px 12px;
      font-size: 11px; overflow: auto; max-height: 320px; white-space: pre-wrap;
      word-break: break-all; }
.chart { background: #fff; border-radius: 8px; padding: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
"""


def _esc(x: Any) -> str:
    return html.escape(str(x))


def _fmt_num(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}"


def _svg_line(points: list[float], width: int, height: int, color: str) -> str:
    if not points:
        return ""
    vmax = max(points) or 1.0
    step = width / max(len(points) - 1, 1)
    pts = " ".join(f"{i * step:.1f},{height - (v / vmax) * (height - 4) - 2:.1f}"
                   for i, v in enumerate(points))
    return (f"<svg width='{width}' height='{height}' style='background:#fafafa'>"
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='1.5'/></svg>")


def render_html(cfg, results: dict, run_name: str) -> str:
    windows = results["windows"]
    judgments = results["judgments"]
    incidents = results["quality_incidents"]

    # 判定汇总
    all_judged = [j for items in judgments.values() for j in items]
    n_pass = sum(1 for j in all_judged if j["passed"] is True)
    n_fail = sum(1 for j in all_judged if j["passed"] is False)
    n_na = sum(1 for j in all_judged if j["passed"] is None)

    stat_cards = "".join(
        f"<div class='stat {cls}'><div class='num'>{num}</div><div class='lbl'>{lbl}</div></div>"
        for cls, num, lbl in [
            ("", results["total_requests"], "总请求"),
            ("", len(windows), "窗口数"),
            ("pass", n_pass, "判定通过"),
            ("fail", n_fail, "判定失败"),
            ("na", n_na, "无法判定"),
            ("fail" if incidents else "pass", len(incidents), "质量事故"),
        ])

    # 判定矩阵
    matrix_rows = []
    for phase, items in judgments.items():
        for j in items:
            cls = "ok" if j["passed"] is True else ("ng" if j["passed"] is False else "na")
            mark = "通过" if j["passed"] is True else ("失败" if j["passed"] is False else "N/A")
            matrix_rows.append(
                f"<tr><td>{_esc(phase)}</td><td>{_esc(j['criterion'])}</td>"
                f"<td>{_esc(j['target'])}</td><td>{_esc(j['actual'])}</td>"
                f"<td class='{cls}'>{mark}</td></tr>")
    matrix = ("<table><tr><th>阶段</th><th>判据</th><th>目标</th>"
              f"<th>实际</th><th>结论</th></tr>{''.join(matrix_rows)}</table>")

    # 基线
    baseline_rows = []
    for b in results.get("baseline", []):
        cls = "ok" if b["pass"] else "ng"
        baseline_rows.append(
            f"<tr><td>{_esc(b['tier'])}</td><td>{b['n']}</td>"
            f"<td>{_fmt_num(b['p50'])} / ≤{b['p50_max']}</td>"
            f"<td>{_fmt_num(b['p90'])} / ≤{b['p90_max']}</td>"
            f"<td class='{cls}'>{'通过' if b['pass'] else '失败'}</td></tr>")
    baseline = ("<table><tr><th>档位</th><th>探针数</th><th>P50(s)/上限</th>"
                f"<th>P90(s)/上限</th><th>结论</th></tr>{''.join(baseline_rows)}</table>")

    # 窗口明细
    win_rows = []
    for w in windows:
        ttft_cells = []
        for tier, t in w["ttft"].items():
            if t["n"] > 0:
                cls = "ok" if t["pass"] else "ng"
                ttft_cells.append(
                    f"<td class='{cls}'>{tier}<br>p50={_fmt_num(t['p50'])} p90={_fmt_num(t['p90'])}"
                    f"<br><small>n={t['n']}</small></td>")
        otps_cls = "ok" if w["otps_violation_ratio"] <= 0.01 else "ng"
        fail_cls = "ok" if w["failure_rate"] < 0.01 else "ng"
        win_rows.append(
            f"<tr><td>w{w['window_id']}<br><small>{w['start']}</small></td>"
            f"<td>{w['total']}</td><td>{_fmt_num(w['rpm'])}</td>"
            f"<td>{_fmt_num(w['tpm'])}</td><td>{_fmt_num(w['uncached_itpm'])}</td>"
            f"<td class='{fail_cls}'>{w['failure_rate']:.2%}</td>"
            f"<td>{w['status']['429']}</td>"
            f"<td class='{otps_cls}'>{w['otps_violation_ratio']:.2%}</td>"
            f"{''.join(ttft_cells)}"
            f"<td>{w['quality_incidents'] or ''}</td></tr>")
    windows_table = (
        "<div class='scroll'><table><tr><th>窗口</th><th>请求</th><th>RPM</th><th>TPM</th>"
        "<th>uncached<br>ITPM</th><th>失败率</th><th>429</th><th>OTPS<br>超标率</th>"
        f"<th colspan='5'>TTFT(s) 按档位</th><th>质量</th></tr>{''.join(win_rows)}</table></div>")

    # 质量事故
    if incidents:
        inc_rows = "".join(
            f"<tr><td>{_esc(i['kind'])}</td><td>{_esc(i['session_id'])}</td>"
            f"<td>{time.strftime('%H:%M:%S', time.localtime(i['ts']))}</td>"
            f"<td>{_esc(i['detail'][:200])}</td></tr>" for i in incidents[:200])
        incidents_table = ("<table><tr><th>类型</th><th>会话</th><th>时间</th>"
                           f"<th>详情</th></tr>{inc_rows}</table>")
    else:
        incidents_table = "<p>无质量事故。</p>"

    # 曲线
    rpm_series = [w["rpm"] for w in windows]
    tpm_series = [w["tpm"] for w in windows]
    charts = (
        f"<div class='chart'><b>RPM</b><br>{_svg_line(rpm_series, 640, 80, '#2563eb')}</div>"
        f"<div class='chart'><b>TPM</b><br>{_svg_line(tpm_series, 640, 80, '#7c3aed')}</div>")

    meta = {
        "模型": cfg.model, "Endpoint": cfg.base_url, "运行": run_name,
        "约定并发": cfg.agreed_concurrency, "约定 TPM": f"{cfg.agreed_tpm:,}",
        "窗口": f"{cfg.window_s}s", "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_rows = " &nbsp; ".join(
        f"<span>{_esc(k)}: <code>{_esc(v)}</code></span>" for k, v in meta.items())

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>K3.1 压力测试报告</title><style>{_CSS}</style></head>
<body>
<div class="header"><h1>K3.1 流量外采 — 压力测试报告</h1><div class="meta">{meta_rows}</div></div>
<div class="container">
  <div class="summary">{stat_cards}</div>
  <h2>判定矩阵（合同/压测条款口径）</h2>{matrix}
  <h2>P0 基线（各 TTFT 档位 uncached 探针）</h2>{baseline}
  <h2>窗口明细（10 分钟窗口）</h2>{windows_table}
  <h2>容量曲线</h2>{charts}
  <h2>质量事故（四项检测）</h2>{incidents_table}
</div>
</body></html>"""


def write_outputs(cfg, results: dict, run_dir, run_name: str) -> dict:
    summary = {
        "run": run_name,
        "config": {
            "model": cfg.model, "base_url": cfg.base_url,
            "agreed_concurrency": cfg.agreed_concurrency,
            "agreed_tpm": cfg.agreed_tpm,
            "agreed_uncached_itpm": cfg.agreed_uncached_itpm,
            "load_threshold_tpm": cfg.effective_load_threshold,
            "window_s": cfg.window_s,
        },
        "total_requests": results["total_requests"],
        "judgments": results["judgments"],
        "baseline": results.get("baseline", []),
        "quality_incident_count": len(results["quality_incidents"]),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "quality_incidents.json").write_text(
        json.dumps(results["quality_incidents"], ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.html").write_text(render_html(cfg, results, run_name), encoding="utf-8")
    return summary
