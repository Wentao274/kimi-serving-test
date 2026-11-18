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


def _fmt_axis(v: float) -> str:
    """坐标轴刻度值缩写：1.2k / 3.4M。"""
    if v >= 1_000_000:
        return f"{v / 1_000_000:g}M"
    if v >= 1_000:
        return f"{v / 1_000:g}k"
    return f"{v:g}"


def _nice_max(v: float) -> float:
    """把 Y 轴上限取整到 1/2/2.5/5/10 × 10^n 的整齐刻度（含 5% 头部余量）。"""
    import math
    v = v * 1.05
    if v <= 0:
        return 1.0
    base = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * base:
            return m * base
    return 10 * base


def _svg_chart(windows: list[dict], key: str, color: str, unit: str,
               window_s: int, width: int = 960, height: int = 280,
               ref: tuple[float, str] | None = None) -> str:
    """带横纵坐标轴、刻度数值与单位的容量曲线。

    - X 轴：窗口起始时间（每窗口 window_s 秒），按主导阶段变化画竖直分界；
    - Y 轴：指标值（带单位与网格线），标注峰值/谷值；
    - ref: (数值, 标签) 红色虚线参考线（如约定 TPM）。
    """
    pts = [w[key] for w in windows]
    if not pts:
        return "<p>无窗口数据。</p>"
    labels = [w["start"] for w in windows]
    phases = []
    for w in windows:
        pc = w.get("phase_counts") or {}
        phases.append(max(pc, key=pc.get) if pc else "")
    ml, mr, mt, mb = 64, 16, 24, 42          # 四边留白（左刻度/下时间轴）
    pw, ph = width - ml - mr, height - mt - mb
    n = len(pts)
    vmax = _nice_max(max([max(pts)] + ([ref[0]] if ref else [])))

    def X(i: int) -> float:
        return ml + pw * i / max(n - 1, 1)

    def Y(v: float) -> float:
        return mt + ph - (v / vmax) * ph

    p = [f"<svg width='{width}' height='{height}' style='background:#fff'>"]
    # Y 轴网格 + 刻度值
    for i in range(6):
        v = vmax * i / 5
        y = Y(v)
        p.append(f"<line x1='{ml}' y1='{y:.1f}' x2='{width - mr}' y2='{y:.1f}' "
                 f"stroke='#e5e7eb' stroke-width='1'/>")
        p.append(f"<text x='{ml - 8}' y='{y + 4:.1f}' text-anchor='end' "
                 f"font-size='11' fill='#6b7280'>{_fmt_axis(round(v))}</text>")
    # Y 轴单位
    p.append(f"<text x='{ml - 8}' y='{mt - 8}' text-anchor='end' font-size='11' "
             f"fill='#374151' font-weight='600'>{_esc(unit)}</text>")
    # X 轴刻度（最多 12 个时间标签）
    step = max(1, -(-n // 12))
    for i in range(0, n, step):
        p.append(f"<text x='{X(i):.1f}' y='{height - mb + 16}' text-anchor='middle' "
                 f"font-size='10' fill='#6b7280'>{_esc(labels[i])}</text>")
    p.append(f"<text x='{(ml + width - mr) / 2:.1f}' y='{height - 8}' text-anchor='middle' "
             f"font-size='11' fill='#374151'>窗口起始时间（每窗口 {window_s}s）</text>")
    # 阶段分界竖线
    for i in range(1, n):
        if phases[i] != phases[i - 1]:
            x = X(i) - pw / max(n - 1, 1) / 2
            p.append(f"<line x1='{x:.1f}' y1='{mt}' x2='{x:.1f}' y2='{mt + ph}' "
                     f"stroke='#d1d5db' stroke-dasharray='3,3'/>")
            p.append(f"<text x='{x + 3:.1f}' y='{mt + 10}' font-size='10' "
                     f"fill='#9ca3af'>{_esc(phases[i])}</text>")
    # 参考线（如约定 TPM）
    if ref:
        rv, rl = ref
        y = Y(rv)
        p.append(f"<line x1='{ml}' y1='{y:.1f}' x2='{width - mr}' y2='{y:.1f}' "
                 f"stroke='#dc2626' stroke-dasharray='5,4' stroke-width='1.2'/>")
        p.append(f"<text x='{width - mr - 4}' y='{y - 5:.1f}' text-anchor='end' "
                 f"font-size='11' fill='#dc2626'>{_esc(rl)}: {_fmt_axis(rv)}</text>")
    # 数据曲线
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(pts))
    p.append(f"<polyline points='{poly}' fill='none' stroke='{color}' stroke-width='1.8'/>")
    # 峰值/谷值标注
    imax = max(range(n), key=lambda i: pts[i])
    imin = min(range(n), key=lambda i: pts[i])
    for idx, name, c in ((imax, "峰值", "#16a34a"), (imin, "谷值", "#dc2626")):
        if idx == imax or n > 1:
            x, y = X(idx), Y(pts[idx])
            anchor = "start" if x < width - 130 else "end"
            dy = -7 if y > mt + 16 else 14
            p.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='{c}'/>")
            p.append(f"<text x='{x:.1f}' y='{y + dy:.1f}' text-anchor='{anchor}' "
                     f"font-size='10' fill='{c}'>{name} {_fmt_axis(pts[idx])}</text>")
    # 坐标轴
    p.append(f"<line x1='{ml}' y1='{mt}' x2='{ml}' y2='{mt + ph}' stroke='#9ca3af'/>")
    p.append(f"<line x1='{ml}' y1='{mt + ph}' x2='{width - mr}' y2='{mt + ph}' stroke='#9ca3af'/>")
    p.append("</svg>")
    return "".join(p)


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

    # 曲线（带坐标轴/刻度/单位；TPM 叠加约定值参考线）
    rpm_chart = _svg_chart(windows, "rpm", "#2563eb", "RPM", cfg.window_s)
    tpm_chart = _svg_chart(windows, "tpm", "#7c3aed", "TPM", cfg.window_s,
                           ref=(cfg.agreed_tpm, "约定TPM"))
    charts = (f"<div class='chart'><b>RPM（请求/分钟）</b><br>{rpm_chart}</div>"
              f"<div class='chart'><b>TPM（tokens/分钟）</b><br>{tpm_chart}</div>")

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
  <h2>窗口明细（{cfg.window_s}s 窗口）</h2>{windows_table}
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
