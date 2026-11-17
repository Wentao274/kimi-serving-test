#!/usr/bin/env python
"""对比供应商与官方两侧工程验收报告，生成对比汇总（供 Jenkins 邮件）。

用法：
    python scripts/gen_compare.py <out_root>

输入（取各自最新一份）：
    <out_root>/engineering_*/report_data.json          → 供应商侧
    <out_root>/official/engineering_*/report_data.json → 官方侧

产出：
    <out_root>/compare.html         逐用例对比表
    <out_root>/compare.properties   汇总键值（键名仅小写字母，便于 Jenkins 解析）
"""

from __future__ import annotations

import glob
import html
import json
import os
import sys

_STATUS_LABEL = {
    "both_pass": "双边均通过",
    "vendor_only_fail": "仅供应商失败",
    "official_only_fail": "仅官方失败",
    "both_fail": "双边均失败",
    "other": "其他（跳过/缺失）",
}


def _latest(pattern: str) -> str | None:
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {r["case_id"]: r for r in d["records"]}, d["summary"]


def main() -> int:
    out_root = sys.argv[1]
    vendor_path = _latest(os.path.join(out_root, "engineering_*", "report_data.json"))
    official_path = _latest(os.path.join(out_root, "official", "engineering_*", "report_data.json"))
    if not vendor_path or not official_path:
        print(f"[gen_compare] 缺少一侧报告，跳过对比（vendor={vendor_path}, official={official_path}）")
        return 0

    vrec, vsum = _load(vendor_path)
    orec, osum = _load(official_path)
    all_ids = sorted(set(vrec) | set(orec))

    cats: dict[str, list[str]] = {k: [] for k in _STATUS_LABEL}
    rows = []
    for cid in all_ids:
        v, o = vrec.get(cid), orec.get(cid)
        vo = v["outcome"] if v else "(未执行)"
        oo = o["outcome"] if o else "(未执行)"
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
        cats[status].append(cid)
        rows.append((cid, vo, oo, status))

    vendor_rate = round(vsum["passed"] / max(vsum["total"], 1) * 100, 2)
    official_rate = round(osum["passed"] / max(osum["total"], 1) * 100, 2)

    # ---------- compare.html ----------
    def esc(x):
        return html.escape(str(x))

    body_rows = "".join(
        f"<tr class='{st}'><td>{esc(cid)}</td><td>{esc(vo)}</td><td>{esc(oo)}</td>"
        f"<td>{esc(_STATUS_LABEL[st])}</td></tr>"
        for cid, vo, oo, st in rows
    )
    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>工程验收 供应商 vs 官方 对比</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 5px 8px; text-align: left; }}
th {{ background: #f3f4f6; }}
.summary td {{ font-weight: 700; }}
tr.vendor_only_fail td {{ background: #fee2e2; }}
tr.official_only_fail td {{ background: #fef3c7; }}
tr.both_fail td {{ background: #f3f4f6; }}
</style></head><body>
<h2>工程验收对比：供应商 vs 官方</h2>
<table class="summary">
<tr><th></th><th>总用例</th><th>通过</th><th>通过率</th></tr>
<tr><td>供应商</td><td>{vsum['total']}</td><td>{vsum['passed']}</td><td>{vendor_rate}%</td></tr>
<tr><td>官方</td><td>{osum['total']}</td><td>{osum['passed']}</td><td>{official_rate}%</td></tr>
<tr><td>双边均通过</td><td colspan="3">{len(cats['both_pass'])}</td></tr>
<tr><td>仅供应商失败</td><td colspan="3">{len(cats['vendor_only_fail'])}</td></tr>
<tr><td>仅官方失败</td><td colspan="3">{len(cats['official_only_fail'])}</td></tr>
<tr><td>双边均失败</td><td colspan="3">{len(cats['both_fail'])}</td></tr>
</table>
<h3>逐用例对比</h3>
<table><tr><th>用例</th><th>供应商</th><th>官方</th><th>对比结论</th></tr>{body_rows}</table>
</body></html>"""
    with open(os.path.join(out_root, "compare.html"), "w", encoding="utf-8") as f:
        f.write(page)

    # ---------- compare.properties（键名仅小写字母） ----------
    props = {
        "vendortotal": vsum["total"],
        "vendorpassed": vsum["passed"],
        "vendorrate": vendor_rate,
        "officialtotal": osum["total"],
        "officialpassed": osum["passed"],
        "officialrate": official_rate,
        "bothpass": len(cats["both_pass"]),
        "vendoronlyfail": len(cats["vendor_only_fail"]),
        "officialonlyfail": len(cats["official_only_fail"]),
        "bothfail": len(cats["both_fail"]),
    }
    with open(os.path.join(out_root, "compare.properties"), "w", encoding="utf-8") as f:
        for k, v in props.items():
            f.write(f"{k}={v}\n")
    print(f"[gen_compare] {props}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
