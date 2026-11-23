"""报告渲染：单文件 HTML（三场景合一）+ summary.json + metrics.jsonl。

HTML 结构：①头部信息栏 ②总判定矩阵 ③TTFT 分档详表+时序散点 ④TPOT 指标表+直方图
⑤缓存命中率 ⑥TTL ⑦异常与剔除样本。内联样式 + SVG，无外部依赖。
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

_CSS = """
body{font-family:'Segoe UI','Microsoft YaHei',Arial,sans-serif;margin:0 auto;max-width:1180px;
padding:24px 32px;color:#1f2937;background:#f5f7fb;font-size:14px;line-height:1.65}
h1{font-size:22px;margin:8px 0}h2{font-size:17px;margin:26px 0 10px;color:#1e3a8a}
table{border-collapse:collapse;width:100%;margin:10px 0 18px;background:#fff;font-size:13px}
th{background:#e3edfc;color:#1e3a8a;font-weight:600}
th,td{border:1px solid #d8dfeb;padding:6px 10px;text-align:left;vertical-align:top}
.card{background:#fff;border:1px solid #d8dfeb;border-radius:8px;padding:14px 18px;margin:12px 0}
.banner{padding:14px 20px;border-radius:8px;color:#fff;font-size:16px;font-weight:600;margin:14px 0}
.pass{background:#2e7d32}.fail{background:#c62828}.warn{background:#ef6c00}
.meta{color:#4b5563;font-size:13px}.ok{color:#2e7d32;font-weight:600}.bad{color:#c62828;font-weight:600}
.soft{color:#ef6c00;font-weight:600}.chart{margin:6px 0 14px}
.small{font-size:12px;color:#6b7280}
"""


def _esc(s) -> str:
    return html.escape(str(s))


def _fmt(v, nd=1) -> str:
    return "-" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def _mark(ok) -> str:
    if ok is True:
        return '<span class="ok">PASS</span>'
    if ok is False:
        return '<span class="bad">FAIL</span>'
    return '<span class="soft">N/A</span>'


def _scatter_svg(series: list[float], avg_limit: float, p90_limit: float,
                 width: int = 760, height: int = 130) -> str:
    """TTFT 时序散点（内联 SVG）+ avg/P90 达标参考线。"""
    if not series:
        return ""
    vmax = max(max(series), p90_limit) * 1.08
    n = len(series)
    pts = []
    for i, v in enumerate(series):
        x = 8 + (width - 16) * (i / max(n - 1, 1))
        y = height - 10 - (height - 20) * (v / vmax)
        color = "#c62828" if v > p90_limit else "#1e88e5"
        pts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}" opacity="0.65"/>')
    lines = []
    for lv, color, label in ((avg_limit, "#ef6c00", f"avg线 {avg_limit:.0f}"),
                             (p90_limit, "#c62828", f"P90线 {p90_limit:.0f}")):
        y = height - 10 - (height - 20) * (lv / vmax)
        lines.append(f'<line x1="8" y1="{y:.1f}" x2="{width - 8}" y2="{y:.1f}" '
                     f'stroke="{color}" stroke-dasharray="5,3" stroke-width="1.2"/>'
                     f'<text x="{width - 8}" y="{y - 3:.1f}" font-size="10" fill="{color}" '
                     f'text-anchor="end">{label}</text>')
    return (f'<svg class="chart" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(lines) + "".join(pts) + "</svg>")


def _histogram_svg(series: list[float], limit: float,
                   width: int = 760, height: int = 130, buckets: int = 12) -> str:
    """TPOT 分布直方图（内联 SVG）+ 达标参考线。"""
    if not series:
        return ""
    vmax = max(max(series), limit) * 1.08
    step = vmax / buckets
    counts = [0] * buckets
    for v in series:
        counts[min(int(v // step), buckets - 1)] += 1
    cmax = max(counts) or 1
    bars = []
    bw = (width - 16) / buckets
    for i, c in enumerate(counts):
        h = (height - 26) * (c / cmax)
        x = 8 + i * bw
        bars.append(f'<rect x="{x:.1f}" y="{height - 16 - h:.1f}" width="{bw - 2:.1f}" '
                    f'height="{h:.1f}" fill="#90caf9"/>'
                    f'<text x="{x + bw / 2:.1f}" y="{height - 4}" font-size="9" '
                    f'text-anchor="middle" fill="#6b7280">{i * step:.0f}</text>')
    lx = 8 + (width - 16) * (limit / vmax)
    ref = (f'<line x1="{lx:.1f}" y1="6" x2="{lx:.1f}" y2="{height - 16}" '
           f'stroke="#c62828" stroke-dasharray="5,3" stroke-width="1.2"/>'
           f'<text x="{lx + 3:.1f}" y="14" font-size="10" fill="#c62828">avg达标线 {limit}ms</text>')
    return (f'<svg class="chart" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(bars) + ref + "</svg>")


def _rows(cells_list: list[list], header: list[str]) -> str:
    th = "".join(f"<th>{_esc(h)}</th>" for h in header)
    trs = []
    for cells in cells_list:
        trs.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return f"<table><tr>{th}</tr>{''.join(trs)}</table>"


def render(out_dir: Path, cfg: dict, ttft_result: dict | None,
           cache_result: dict | None, started: str, elapsed_s: float,
           deploy_id: str) -> tuple[Path, dict]:
    """渲染三件套，返回 (html_path, summary)。"""
    model = cfg["model"]
    stamp = out_dir.name
    safe_model = "".join(c if (c.isalnum() or c in "._-") else "_" for c in model)
    html_name = f"{safe_model}_selfstress1_report_{stamp.replace('_', '')}.html"

    # ---- 判定矩阵 ----
    matrix_rows = []
    if ttft_result:
        for t in ttft_result["tiers"]:
            matrix_rows.append([
                f"TTFT {_esc(t['name'])}",
                f"avg {_fmt(t['avg_ms'])}ms / P90 {_fmt(t['p90_ms'])}ms",
                f"≤{t['avg_limit']:.0f} / ≤{t['p90_limit']:.0f} ms", _mark(t["passed"])])
        tp = ttft_result["tpot"]
        matrix_rows.append([
            "TPOT", f"avg {_fmt(tp['avg_ms'])} / P50 {_fmt(tp['p50_ms'])} / "
                    f"P90 {_fmt(tp['p90_ms'])} ms",
            f"≤{tp['limits']['avg']} / ≤{tp['limits']['p50']} / ≤{tp['limits']['p90']} ms",
            _mark(tp["passed"])])
    if cache_result:
        hr = cache_result["hit_rate"]
        matrix_rows.append([
            "缓存命中率", f"avg {hr['avg']:.1%} / min {hr['min']:.1%}",
            f"≥{hr['limit']:.0%}", _mark(hr["passed"])])
        ttl = cache_result["ttl"]
        n_hit = sum(1 for r in ttl["rows"] if r["hit"])
        matrix_rows.append([
            f"缓存 TTL（{ttl['wait_s']:.0f}s 仍命中）",
            f"{n_hit}/{len(ttl['rows'])} 轮命中", "全部命中", _mark(ttl["passed"])])

    overall = all([
        ttft_result["passed"] if ttft_result else True,
        cache_result["passed"] if cache_result else True,
    ])
    banner = (f'<div class="banner {"pass" if overall else "fail"}">'
              f'总判定：{"PASS" if overall else "FAIL"}（TTFT/TPOT + 缓存基线）</div>')

    # ---- TTFT 详表 + 散点 ----
    ttft_html = ""
    if ttft_result:
        rows = []
        for t in ttft_result["tiers"]:
            rows.append([
                _esc(t["name"]), _fmt(t.get("target_tokens", "-")),
                f"{t['n_ok']}/{t['n_planned']}",
                _fmt(t["avg_ms"]), _fmt(t["p90_ms"]),
                _fmt(t["baseline_avg"], 0), _fmt(t["baseline_p90"], 0),
                f"{t['avg_limit']:.0f}", f"{t['p90_limit']:.0f}", _mark(t["passed"])])
        ttft_html += _rows(rows, ["区间", "目标tokens", "样本(成功/计划)", "实测avg(ms)",
                                  "实测P90(ms)", "基线avg", "基线P90", "达标avg", "达标P90", "判定"])
        for t in ttft_result["tiers"]:
            ttft_html += (f"<h2>TTFT 时序 — {_esc(t['name'])}</h2>"
                          + _scatter_svg(t.get("ttft_series", []), t["avg_limit"], t["p90_limit"]))
            bad = [j for j in t["judgments"] if j["passed"] is False]
            if bad:
                ttft_html += "<p class='small'>未达标：" + "；".join(_esc(j["detail"]) for j in bad) + "</p>"

    # ---- TPOT ----
    tpot_html = ""
    if ttft_result:
        tp = ttft_result["tpot"]
        rows = [
            ["avg", _fmt(tp["avg_ms"]), "25", str(tp["limits"]["avg"]), _mark(tp["judgments"][0]["passed"])],
            ["P50", _fmt(tp["p50_ms"]), "29", str(tp["limits"]["p50"]), _mark(tp["judgments"][1]["passed"])],
            ["P90", _fmt(tp["p90_ms"]), "35", str(tp["limits"]["p90"]), _mark(tp["judgments"][2]["passed"])],
        ]
        tpot_html += _rows(rows, ["指标", "实测(ms)", "基线(ms)", "达标线(ms)", "判定"])
        tpot_html += _histogram_svg(tp.get("series", []), tp["limits"]["avg"])
        tpot_html += f"<p class='small'>有效样本 {tp['n']} 个请求（逐请求 TPOT = 流式内容区间/(completion_tokens−1)）</p>"

    # ---- 缓存 ----
    cache_html = ""
    if cache_result:
        hr = cache_result["hit_rate"]
        rows = [[r["round"], _fmt(r.get("prompt_tokens"), 0), _fmt(r.get("cached_tokens"), 0),
                 f"{r['hit_rate']:.1%}", _mark(r["hit"])] for r in hr["rows"]]
        cache_html += ("<h2>缓存命中率（90% 前缀重复）</h2>"
                       + _rows(rows, ["轮次", "prompt_tokens", "cached_tokens", "hit_rate", "命中"])
                       + f"<p>avg <b>{hr['avg']:.1%}</b>（达标 ≥{hr['limit']:.0%}）/ "
                         f"min {hr['min']:.1%}（方法节参考线 {hr['reference']:.0%}）"
                         f" → {_mark(hr['passed'])}</p>")
        ttl = cache_result["ttl"]
        rows = [[r["round"], f"{r['wait_s']:.0f}s", _fmt(r.get("cached_tokens"), 0),
                 f"{r['hit_rate']:.1%}", _mark(r["hit"])] for r in ttl["rows"]]
        cache_html += (f"<h2>缓存 TTL（间隔 {ttl['wait_s']:.0f}s 仍命中，"
                       f"hit_rate ≥{ttl['min_hit_rate']:.0%}）</h2>"
                       + _rows(rows, ["轮次", "等待", "cached_tokens", "hit_rate", "命中"])
                       + f"<p>{sum(1 for r in ttl['rows'] if r['hit'])}/{len(ttl['rows'])} 轮命中"
                         f" → {_mark(ttl['passed'])}</p>")
        ep = cache_result.get("expire_probe")
        if ep:
            cache_html += (f"<p class='small'>过期观察（{ep['wait_s']:.0f}s）:"
                           f"hit_rate={ep['hit_rate']:.1%}，命中={ep['hit']}"
                           f"（对照原厂 ~50s，记录不判定）</p>")

    # ---- 异常与剔除 ----
    anomalies = []
    if ttft_result:
        for r in ttft_result["records"]:
            if r["status"] != 200 or r["error"]:
                anomalies.append(["ttft", r.get("planned_tier", ""), str(r["status"]),
                                  _esc((r["error"] or "")[:160])])
        cold_bad = [r for r in ttft_result["records"]
                    if r["status"] == 200 and not r["error"] and not r["cold_ok"]]
        if cold_bad:
            anomalies.append(["ttft", "冷请求违例", f"{len(cold_bad)} 例",
                              "cached_tokens>0（样本已从判定剔除）"])
    if cache_result:
        for r in cache_result["records"]:
            if r.get("error") or (r.get("status") not in (None, 200)):
                anomalies.append(["cache", r.get("phase", ""), str(r.get("status", "-")),
                                  _esc((r.get("error") or "")[:160])])
    anom_html = (_rows(anomalies[:50], ["场景", "位置/档", "status", "详情"])
                 if anomalies else "<p class='small'>无异常样本</p>")

    # ---- 头部 ----
    mode = "quick" if cfg["ttft_tpot"].get("quick_mode") else "full"
    header = f"""
<div class="card">
  <h1>K3.1-Pro 性能基线报告（k31selfstress1）</h1>
  <div class="meta">
    模型：<b>{_esc(model)}</b> ｜ Endpoint：{_esc(cfg['base_url'])} ｜
    部署版本：{_esc(deploy_id or '-')} ｜ 模式：{mode}<br/>
    开始：{_esc(started)} ｜ 耗时：{elapsed_s:.1f}s ｜ 配置：{_esc(cfg.get('_config_path', '-'))}<br/>
    关键参数：concurrency={cfg['ttft_tpot']['concurrency']} ｜ samples/档={cfg['ttft_tpot']['samples_per_tier']} ｜
    max_tokens={cfg['ttft_tpot']['max_tokens']} ｜ include_usage={cfg['ttft_tpot'].get('include_usage')} ｜
    TTL等待={cfg['cache']['ttl_wait_s']}s
  </div>
</div>{banner}"""

    body = (f"<html><head><meta charset='utf-8'><title>K3.1-Pro 性能基线报告</title>"
            f"<style>{_CSS}</style></head><body>"
            + header
            + "<h2>总判定矩阵</h2>"
            + _rows(matrix_rows, ["场景/指标", "实测", "达标线", "判定"])
            + "<h2>场景一：TTFT（按输入长度分档）</h2>" + ttft_html
            + "<h2>场景一：TPOT</h2>" + tpot_html
            + cache_html
            + "<h2>异常与剔除样本</h2>" + anom_html
            + "<p class='small'>k31selfstress1 · 数据来源：metrics.jsonl（不含原始请求/响应文本）"
              f" · 生成时间 {time.strftime('%Y-%m-%d %H:%M:%S')}</p>"
            + "</body></html>")

    html_path = out_dir / html_name
    html_path.write_text(body, encoding="utf-8")

    # ---- summary.json ----
    n_req = (ttft_result or {}).get("n_requests", 0) + (cache_result or {}).get("n_requests", 0)
    n_judg_pass = sum(1 for row in matrix_rows if "PASS" in str(row[-1]))
    n_judg_fail = sum(1 for row in matrix_rows if "FAIL" in str(row[-1]))
    summary = {
        "suite": "k31selfstress1", "model": model, "report_html": html_name,
        "started_at": started, "elapsed_s": round(elapsed_s, 1), "mode": mode,
        "result": "PASS" if overall else "FAIL",
        "ttft": ttft_result and {
            "tiers": [{k: t[k] for k in ("name", "n_ok", "n_planned", "avg_ms", "p90_ms",
                                         "avg_limit", "p90_limit", "passed")}
                      for t in ttft_result["tiers"]],
            "tpot": {k: ttft_result["tpot"][k] for k in ("n", "avg_ms", "p50_ms", "p90_ms",
                                                        "limits", "passed")},
            "passed": ttft_result["passed"],
        },
        "cache": cache_result and {
            "hit_rate_avg": cache_result["hit_rate"]["avg"],
            "hit_rate_min": cache_result["hit_rate"]["min"],
            "limit": cache_result["hit_rate"]["limit"],
            "passed": cache_result["hit_rate"]["passed"],
            "ttl": {"wait_s": cache_result["ttl"]["wait_s"],
                    "rounds": len(cache_result["ttl"]["rows"]),
                    "hits": sum(1 for r in cache_result["ttl"]["rows"] if r["hit"]),
                    "passed": cache_result["ttl"]["passed"]},
            "expire_probe": cache_result.get("expire_probe"),
            "passed": cache_result["passed"],
        },
        "stats": {"total": n_req, "passed": n_judg_pass, "failed": n_judg_fail,
                  "rate": round(n_judg_pass / (n_judg_pass + n_judg_fail) * 100, 2)
                  if (n_judg_pass + n_judg_fail) else 0.0},
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- metrics.jsonl ----
    with (out_dir / "metrics.jsonl").open("w", encoding="utf-8") as f:
        if ttft_result:
            for r in ttft_result["records"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if cache_result:
            for r in cache_result["records"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return html_path, summary
