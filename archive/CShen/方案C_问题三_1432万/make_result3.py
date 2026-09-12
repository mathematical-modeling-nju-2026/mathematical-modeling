"""生成 result3.xlsx（严格遵循附件5/result3.xlsx 模板）。

模板结构（4 个工作表）
  计划购电量：334 天 × [日期, 144 时段(kWh), 全天购电量, 全天购电费]
  调整购电量：同结构，保存各时段"调整后购电量 g_adj"（最终执行值）
  充放电量  ：334 天 × 6 个 4 小时块（充电量/放电量）+ 0:00/24:00 储电量
  紧急购电量：日期 + 购电时间段 + 购电量

说明
  模板"计划购电量"的 144 个时间标签为 0:10-0:20 ... 0:00-0:10+1（右端标签），
  列 j(1-based) 的左端时刻 = (j-1)*10 分钟 → 列 j ↔ 内部时段索引 j-1（0-based）。
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import time

import numpy as np
import openpyxl
from openpyxl.styles import Font, Alignment

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_q3 as R
from q3_data import T, DT

ATT = Path(r"d:\数学建模大赛\CUMCM2026Problems\C题\附件")
TPL = ATT / "附件5" / "result3.xlsx"


def template_labels():
    ws = openpyxl.load_workbook(TPL, data_only=True)["计划购电量"]
    head = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    labs = [str(x) for x in head[1:1 + T]]
    assert len(labs) == T, len(labs)
    return labs


def _lbl_hm(t):
    m = t * 10
    return "0:00+1" if m >= 1440 else f"{m // 60}:{m % 60:02d}"


def merge_intervals(e, tol=1e-6):
    out, t = [], 0
    while t < T:
        if e[t] > tol:
            t0, q = t, 0.0
            while t < T and e[t] > tol:
                q += e[t]; t += 1
            out.append((t0, t, q))
        else:
            t += 1
    return [(_lbl_hm(a), _lbl_hm(b), q) for a, b, q in out]


def export(result, path):
    labels = template_labels()
    g_plan = result["g_plan"]          # 计划购电量 (kWh/时段)
    g_adj = result["g_final"]          # 调整后购电量（最终执行）
    c, d, e = result["c"], result["d"], result["e"]
    E_start, E_end = result["E_start"], result["E_end"]
    price = result["price"]
    dates = result["dates"]

    wb = openpyxl.Workbook()
    bold = Font(bold=True)

    # ---- 计划购电量 ----
    ws = wb.active; ws.title = "计划购电量"
    ws.append(["日期\\时间"] + labels + ["全天购电量", "全天购电费"])
    for cc in ws[1]:
        cc.font = bold; cc.alignment = Alignment(horizontal="center")
    for i, dt in enumerate(dates):
        gp = g_plan[i]
        ws.append([dt] + [round(float(v), 4) for v in gp] +
                  [round(float(gp.sum()), 4), round(float(price @ gp), 2)])
    ws.column_dimensions["A"].width = 12
    ws.freeze_panes = "B2"

    # ---- 调整购电量 ----
    ws1 = wb.create_sheet("调整购电量")
    ws1.append(["日期\\时间"] + labels + ["全天购电量", "全天购电费"])
    for cc in ws1[1]:
        cc.font = bold; cc.alignment = Alignment(horizontal="center")
    for i, dt in enumerate(dates):
        ga = g_adj[i]
        ws1.append([dt] + [round(float(v), 4) for v in ga] +
                   [round(float(ga.sum()), 4), round(float(price @ ga), 2)])
    ws1.column_dimensions["A"].width = 12
    ws1.freeze_panes = "B2"

    # ---- 充放电量 ----
    ws2 = wb.create_sheet("充放电量")
    ws2.append(["日期", "时间段", "充电量", "放电量", "时刻", "储电量"])
    for cc in ws2[1]:
        cc.font = bold
    blocks = ["0:00-4:00", "4:00-8:00", "8:00-12:00",
              "12:00-16:00", "16:00-20:00", "20:00-24:00"]
    for i, dt in enumerate(dates):
        for b, nm in enumerate(blocks):
            t0, t1 = b * 24, (b + 1) * 24
            ws2.append([dt if b == 0 else None, nm,
                        round(float(c[i, t0:t1].sum()), 4),
                        round(float(d[i, t0:t1].sum()), 4),
                        time(0, 0) if b == 0 else ("24:00" if b == 1 else None),
                        round(float(E_start[i]), 4) if b == 0
                        else (round(float(E_end[i]), 4) if b == 1 else None)])
    for col, wd in zip("ABCDEF", (12, 14, 12, 12, 10, 12)):
        ws2.column_dimensions[col].width = wd

    # ---- 紧急购电量 ----
    ws3 = wb.create_sheet("紧急购电量")
    ws3.append(["日期", "购电时间段", "购电量"])
    for cc in ws3[1]:
        cc.font = bold
    for i, dt in enumerate(dates):
        ivs = merge_intervals(e[i])
        if not ivs:
            ws3.append([dt, "—", 0.0]); continue
        for j, (lab0, lab1, q) in enumerate(ivs):
            ws3.append([dt if j == 0 else None, f"{lab0}-{lab1}", round(q, 4)])
    for col, wd in zip("ABC", (12, 20, 12)):
        ws3.column_dimensions[col].width = wd

    wb.save(path)


if __name__ == "__main__":
    print("仿真中（6/12/18 调整）...")
    res = R.simulate(use_adjust=True, verbose=False)
    s = R.summarize(res)
    print(f"总费用={s['total_wan']:.2f}万（计划{s['plan_cost']/1e4:.2f}/"
          f"调整{s['dev_cost']/1e4:.2f}/紧急{s['emg_cost']/1e4:.2f}）")
    out = HERE / "result3.xlsx"
    export(res, out)
    print(f"已生成: {out}")
    # 校验
    np.savez(HERE / "_q3_result.npz",
             dates=np.array([d.strftime("%Y-%m-%d") for d in res["dates"]]),
             g_plan=res["g_plan"], g_final=res["g_final"], c=res["c"],
             d=res["d"], z=res["z"], e=res["e"],
             E_start=res["E_start"], E_end=res["E_end"], N=res["N"],
             price=res["price"])
