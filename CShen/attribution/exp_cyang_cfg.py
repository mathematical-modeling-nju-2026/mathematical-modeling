"""实验 v4：用 C_yang 的精确配置（L[sw4/d5]+V[t7/d28], H=2, 56场景）接入 P3 框架。

定位 1460.9 万 与 1438.9 万 的差距来源。
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "opt_v3"))
CY = Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\q2")
sys.path.insert(0, str(CY))

from forecast import load_data as load_mine, DT_HOURS, SLOTS
from optimization import PARAM, execute_day
from experiment_inequality2 import solve_horizon

import q2_data, q2_forecast

RAW = Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\raw")
data = load_mine(RAW)
price = data.price
START_DAY, ND = 31, len(data.dates)

_, Lc, Vc = q2_data.load_attachment2()   # (dates, L_kW(365,144), V_kW(365,144))


def run(H=2, lookback=56, cy_pred=True):
    # 预测矩阵（kWh）
    fL = np.zeros((ND, SLOTS)); fV = np.zeros((ND, SLOTS))
    if cy_pred:
        fc = q2_forecast.Forecaster("sw4", 5, "t7", 28)
        for d in range(ND):
            pl = fc.channel_load(Lc, d)
            pv = fc.channel_pv(Vc, d)
            fL[d] = np.asarray(pl, float) * DT_HOURS
            fV[d] = np.asarray(pv, float) * DT_HOURS
    else:
        from forecast import build_forecasts
        b = build_forecasts(data)
        fL = b.load_kwh[:, 0]; fV = b.pv_kwh[:, 0]

    e_state = PARAM.initial_energy_kwh
    tp = te = tc = 0.0
    for di in range(START_DAY, ND):
        h = min(H, ND - di)
        origins = np.arange(max(7, di - lookback), di)
        ls, ps = [], []
        for j in origins:
            lr = data.load_kw[j] * DT_HOURS - fL[j]
            pr = data.pv_kw[j] * DT_HOURS - fV[j]
            ls.append(np.maximum(fL[di] + lr, 0.0))
            ps.append(np.maximum(fV[di] + pr, 0.0))
        N_scen = (np.asarray(ls) - np.asarray(ps)).reshape(len(origins), -1)
        w = np.full(len(origins), 1.0/len(origins))
        N_plan = np.zeros((h, SLOTS))
        for k in range(h):
            kk = di + k if di + k < ND else di
            N_plan[k] = fL[kk] - fV[kk]
        prices = np.tile(price, h)
        plan = solve_horizon(N_plan.reshape(-1), N_scen, w, e_state, h, True)
        al = data.load_kw[di] * DT_HOURS
        ap = data.pv_kw[di] * DT_HOURS
        ex = execute_day(plan, al, ap, price, e_state)
        tp += float(ex["planned_cost_yuan"].sum())
        te += float(ex["emergency_cost_yuan"].sum())
        tc += float(ex["surplus_kwh"].sum())
        e_state = float(ex["energy_end_kwh"][-1])
    return tp, te, tc


print("=" * 76)
print("用 C_yang 精确配置接入 P3 框架")
print("=" * 76)
for cy, lb, desc in [(True, 56, "V1 C_yang预测器 + 56场景 + 48h不等式周期终端"),
                     (True, 28, "V2 C_yang预测器 + 28场景 + 48h不等式周期终端"),
                     (True, 120, "V3 C_yang预测器 + 120场景 + 48h不等式周期终端")]:
    pc, ec, cur = run(2, lb, cy)
    print(f"{desc}")
    print(f"   计划费={pc/1e4:>8.1f}万 紧急费={ec/1e4:>7.1f}万 "
          f"总={(pc+ec)/1e4:>8.1f}万 弃电={cur/1e4:.1f}万kWh")
print()
print("对照: C_yang 官方 1438.9 万 | 我方预测器 P3 = 1460.9 万")
