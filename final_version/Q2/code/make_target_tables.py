"""为问题2 生成题目要求的「表1/表2/表3」数据结构。

题目要求（问题2）：
  · 按表1 格式给出 4 个指定日期的计划购电量（指定 10 分钟时段）+ 全天购电量/购电费
  · 按表2 格式给出储能设备在指定时间段的充放电量 + 0:00 与 24:00 储电量
  · 按表3 格式给出紧急购电量（全部紧急时间区间）

指定日期：2025-03-20、2025-06-21、2025-09-23、2025-12-21
指定 10 分钟时段：10:00-10:10、12:00-12:10、14:00-14:10、16:00-16:10、18:00-18:10、20:00-20:10
指定 4 小时时段：0:00-4:00、4:00-8:00、8:00-12:00、12:00-16:00、16:00-20:00、20:00-24:00

输入：question2/results/schedule_detail.csv.gz
输出：question2/results/target_table1.csv / target_table2.csv / target_table3.csv
      question2/results/target_daily.csv
"""
from __future__ import annotations

import pathlib

import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
RES = REPO / "question2" / "results"
DETAIL = RES / "schedule_detail.csv.gz"

TARGETS = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
SLOTS = [10, 12, 14, 16, 18, 20]          # 指定 10 分钟时段的起点小时
BLOCKS = 6                                # 6 个 4 小时块
T = 144


def intervals(values, tol=1e-7):
    """把逐时段量压缩成连续区间的 (起止标签, 合计)。"""
    start = None
    n = len(values)
    for t in range(n + 1):
        active = t < n and values[t] > tol
        if active and start is None:
            start = t
        elif not active and start is not None:
            a = f"{start * 10 // 60:02d}:{start * 10 % 60:02d}"
            b = "24:00" if t == n else f"{t * 10 // 60:02d}:{t * 10 % 60:02d}"
            yield f"{a}-{b}", float(values[start:t].sum())
            start = None


def main():
    det = pd.read_csv(DETAIL)
    print(f"读入 {DETAIL.name}: {det.shape[0]:,} 行，{det.date.nunique()} 天")

    r1, r2, r3, rd = [], [], [], []
    for date in TARGETS:
        g = det[det.date == date].reset_index(drop=True)
        if not len(g):
            print(f"  ! {date} 无数据，跳过")
            continue
        assert len(g) == T, f"{date} 段数 {len(g)} != {T}"

        # ---- 表1：指定 10 分钟时段的计划购电量 ----
        for h in SLOTS:
            r = g.iloc[h * 6]
            r1.append(dict(date=date, span=f"{r['start']}-{r['end']}",
                           planned_kwh=float(r["g_kwh"])))
        # 全天合计
        r1.append(dict(date=date, span="全天",
                       planned_kwh=float(g["g_kwh"].sum())))

        # ---- 表2：6 个 4 小时块的充放电量 + 首末储电量 ----
        for b in range(BLOCKS):
            blk = g.iloc[b * 24:(b + 1) * 24]
            a = f"{b * 4:02d}:00"
            bb = "24:00" if b == 5 else f"{(b + 1) * 4:02d}:00"
            r2.append(dict(date=date, span=f"{a}-{bb}",
                           charge_kwh=float(blk["c_kwh"].sum()),
                           discharge_kwh=float(blk["d_kwh"].sum())))
        r2.append(dict(date=date, span="0:00储电量",
                       charge_kwh=float(g.iloc[0]["energy_before_kwh"]),
                       discharge_kwh=None))
        r2.append(dict(date=date, span="24:00储电量",
                       charge_kwh=float(g.iloc[-1]["energy_after_kwh"]),
                       discharge_kwh=None))

        # ---- 表3：全部紧急购电区间 ----
        for span, amount in intervals(g["emergency_kwh"].to_numpy()):
            r3.append(dict(date=date, span=span, emergency_kwh=amount))

        # ---- 日汇总 ----
        rd.append(dict(
            date=date,
            planned_kwh_day=float(g["g_kwh"].sum()),
            planned_cost_yuan=float(g["planned_cost_yuan"].sum()),
            emergency_kwh_day=float(g["emergency_kwh"].sum()),
            emergency_cost_yuan=float(g["emergency_cost_yuan"].sum()),
            total_cost_yuan=float(g["total_cost_yuan"].sum()),
            energy_00=float(g.iloc[0]["energy_before_kwh"]),
            energy_24=float(g.iloc[-1]["energy_after_kwh"]),
        ))

    pd.DataFrame(r1).to_csv(RES / "target_table1.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(r2).to_csv(RES / "target_table2.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(r3).to_csv(RES / "target_table3.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(rd).to_csv(RES / "target_daily.csv", index=False, encoding="utf-8-sig")

    print(f"\n已导出：")
    print(f"  target_table1.csv  {len(r1):3d} 行")
    print(f"  target_table2.csv  {len(r2):3d} 行")
    print(f"  target_table3.csv  {len(r3):3d} 行（紧急区间）")
    print(f"  target_daily.csv   {len(rd):3d} 行")
    print()
    print(pd.DataFrame(rd).to_string(index=False))


if __name__ == "__main__":
    main()
