"""诊断：紧急费为何高于同伴（场景权重 vs 分位鲁棒）。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "archive" / "CShen" / "方案C_问题三_1432万"))
from q3_data import load_price, load_actual, load_forecast, T, DT
import run_q3 as R

price = load_price(); L, PV = load_actual(); FC, _ = load_forecast()
load_fc = R.load_forecast_matrix(L)
PVFC = R.build_pv_forecast(FC, PV, "adaptive")
Lres, PVres = R.build_residuals(L, PV, PVFC, load_fc)
N = L - PV

d = np.load(HERE / "_q3_greedy_result.npz", allow_pickle=True)
e = d["e"]; g_final = d["g_final"]; c = d["c"]; dd = d["d"]; Nk = d["N"] * DT
z = g_final + dd - c

print("紧急购电分布:")
et = e.sum(axis=1)
print(f"  有紧急电的天数 {int((et>1e-6).sum())}/334, 总 {e.sum()/1e4:.2f} 万 kWh")
print(f"  单日最大 {et.max():.0f} kWh, 中位 {np.median(et):.0f}")
print()
print("时段级缺口 (N - z) 分布:")
gap = Nk - z
print(f"  >0 占比 {100*(gap>1e-3).mean():.2f}%, 正缺口总量 {gap[gap>0].sum()/1e4:.2f} 万 kWh")
print(f"  分位[50,75,90,95,99]: {np.percentile(gap,[50,75,90,95,99]).round(1)}")
print()
print("z 富余 (>0) 分布:")
exc = z - Nk
print(f"  z>N 占比 {100*(exc>1e-3).mean():.2f}%, 富余总量 {exc[exc>0].sum()/1e4:.2f} 万 kWh")
print(f"  分位[50,75,90,95,99]: {np.percentile(exc,[50,75,90,95,99]).round(1)}")
print()
# 检查计划净供给是否偏高
print(f"计划购电总量 {g_final.sum()/1e4:.1f} 万 kWh")
print(f"实际负载总量 {Nk.sum()/1e4:.1f} 万 kWh")
print(f"充放电净 {c.sum()/1e4:.1f}/{dd.sum()/1e4:.1f} 万 kWh")
