"""诊断：同伴的调整机制为何几乎不生效（净调整费仅 1.44 万）？"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
PEER = Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\ques3")

det = pd.read_csv(PEER / "schedule_detail.csv", encoding="utf-8-sig")
print("=== 调整量分布 ===")
print(f"增购 increase_kwh 总量 {det.increase_kwh.sum()/1e4:.2f} 万 kWh")
print(f"减购 decrease_kwh 总量 {det.decrease_kwh.sum()/1e4:.2f} 万 kWh")
print(f"增购费 {det.increase_cost_yuan.sum()/1e4:.2f} 万")
print(f"退款   {det.cancellation_refund_yuan.sum()/1e4:.2f} 万")
print(f"违约费 {det.breach_cost_yuan.sum()/1e4:.2f} 万")
print(f"净调整 {det.adjustment_net_yuan.sum()/1e4:.2f} 万")
print()
print("有增购的时段数:", int((det.increase_kwh>1e-6).sum()))
print("有减购的时段数:", int((det.decrease_kwh>1e-6).sum()))
print()
print("=== 按 issue_hour 看调整 ===")
g = det.groupby("issue_hour").agg(
    inc=("increase_kwh","sum"), dec=("decrease_kwh","sum"),
    adjcost=("adjustment_net_yuan","sum"), emg=("emergency_kwh","sum"))
print((g/1).round(0).to_string())
print()
print("=== 0:00 块（无法调整）vs 之后 ===")
print(f"0:00-6:00 段：紧急 {det[det.slot<36].emergency_kwh.sum()/1e4:.2f} 万 kWh, "
      f"dump {det[det.slot<36].dump_kwh.sum()/1e4:.2f} 万 kWh")
print(f"6:00 之后 ：紧急 {det[det.slot>=36].emergency_kwh.sum()/1e4:.2f} 万 kWh, "
      f"dump {det[det.slot>=36].dump_kwh.sum()/1e4:.2f} 万 kWh")
print()
print("=== 关键：调整时为什么不多减？看某天细节 ===")
d0 = "2025-09-05"   # dump 第二多
sub = det[det.date == d0]
print(f"{d0}: origin={sub.original_kwh.sum():.0f} adj={sub.adjusted_kwh.sum():.0f} "
      f"dump={sub.dump_kwh.sum():.0f} emg={sub.emergency_kwh.sum():.0f}")
for h in (0, 6, 12, 18):
    seg = sub[sub.slot // 36 == h // 6] if h < 24 else None
    if seg is None or not len(seg):
        continue
    print(f"  issue={h:02d}时: orig={seg.original_kwh.sum():8.0f} "
          f"adj={seg.adjusted_kwh.sum():8.0f} "
          f"inc={seg.increase_kwh.sum():7.0f} dec={seg.decrease_kwh.sum():7.0f} "
          f"emg={seg.emergency_kwh.sum():7.0f} dump={seg.dump_kwh.sum():7.0f}")
