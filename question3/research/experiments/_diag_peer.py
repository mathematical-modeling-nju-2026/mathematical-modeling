"""分析同伴方案的可优化点（不改动其代码，仅诊断）。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
PEER = Path(__file__).resolve().parents[3] / "question3/results"
sys.path.insert(0, str(PEER.parent / "code"))

import pandas as pd
d = pd.read_csv(PEER / "daily_summary.csv", encoding="utf-8-sig")
det = pd.read_csv(PEER / "schedule_detail.csv", encoding="utf-8-sig",
                  usecols=["date", "slot", "price_yuan_per_kwh", "original_kwh",
                           "adjusted_kwh", "charge_kwh", "discharge_kwh",
                           "net_supply_kwh", "emergency_kwh", "dump_kwh",
                           "energy_before_kwh", "energy_after_kwh",
                           "forecast_net_kwh"])
print("=== 同伴方案诊断 ===")
print(f"总费用       {d.total_cost_yuan.sum()/1e4:9.2f} 万")
print(f"  计划费     {d.planned_cost_yuan.sum()/1e4:9.2f} 万")
print(f"  净调整费   {d.adjustment_net_yuan.sum()/1e4:9.2f} 万")
print(f"  紧急费     {d.emergency_cost_yuan.sum()/1e4:9.2f} 万")
print()
print(f"弃置电量 (dump)  {d.dump_kwh.sum()/1e4:9.2f} 万 kWh")
print(f"紧急购电量       {d.emergency_kwh.sum()/1e4:9.2f} 万 kWh")
print(f"原计划购电量     {d.original_kwh.sum()/1e4:9.2f} 万 kWh")
print(f"调整后购电量     {d.adjusted_kwh.sum()/1e4:9.2f} 万 kWh")
print(f"充电/放电        {d.charge_kwh.sum()/1e4:9.2f} / {d.discharge_kwh.sum()/1e4:9.2f} 万 kWh")
print()
# SOC 分布
print(f"SOC 起点范围: {d.energy_start_kwh.min():.0f} ~ {d.energy_start_kwh.max():.0f}")
print(f"SOC 终点范围: {d.energy_end_kwh.min():.0f} ~ {d.energy_end_kwh.max():.0f}")
print(f"SOC 起点=10800(满) 的天数: {(d.energy_start_kwh > 10799).sum()}")
print(f"SOC 起点=1200(空)  的天数: {(d.energy_start_kwh < 1201).sum()}")
print()
print("=== 关键：dump 最多的 10 天 ===")
top = d.nlargest(10, 'dump_kwh')[['date', 'dump_kwh', 'emergency_kwh',
                                  'total_cost_yuan', 'original_kwh', 'adjusted_kwh']]
print(top.to_string(index=False))
print()
print("=== 紧急费最多的 10 天 ===")
top2 = d.nlargest(10, 'emergency_cost_yuan')[['date', 'emergency_cost_yuan',
                                               'emergency_kwh', 'dump_kwh', 'total_cost_yuan']]
print(top2.to_string(index=False))
