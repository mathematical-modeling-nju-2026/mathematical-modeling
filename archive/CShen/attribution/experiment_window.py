"""实验 v3：定位与 C_yang 最新版(1438.9万) 的剩余差距。

固定 P3 配置（48h + 不等式 + 周期终端），依次换用：
  S1. 场景窗口 28 天（我方旧）
  S2. 场景窗口 56 天（C_yang 新版）          ← 测窗口
  S3. 窗口 56 天 + 更多场景（全窗口不削减）  ← 测场景数
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "opt_v3"))

from forecast import load_data, build_forecasts, DT_HOURS, SLOTS, SCENARIO_LOOKBACK
from optimization import PARAM, execute_day
import forecast as FC
from experiment_inequality2 import solve_horizon

RAW = Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\raw")
data = load_data(RAW)
price = data.price
START_DAY = 31
ND = len(data.dates)


def make_scen_custom(bundle, di, lookback):
    """用指定窗口长度构造整日残差场景（复刻 make_scenarios，但窗口可变）。"""
    origins = np.arange(max(7, di - lookback), di)
    load_s, pv_s = [], []
    for j in origins:
        lr = data.load_kw[j] * DT_HOURS - bundle.load_kwh[j, 0]
        pr = data.pv_kw[j] * DT_HOURS - bundle.pv_kwh[j, 0]
        load_s.append(np.maximum(bundle.load_kwh[di, 0] + lr, 0.0))
        pv_s.append(np.maximum(bundle.pv_kwh[di, 0] + pr, 0.0))
    return np.asarray(load_s), np.asarray(pv_s), np.full(len(origins), 1.0/len(origins))


def run(H=2, lookback=28):
    bundle = build_forecasts(data)
    e_state = PARAM.initial_energy_kwh
    tp = te = tc = 0.0
    nscen = []
    for di in range(START_DAY, ND):
        h = min(H, ND - di)
        ls, ps, w = make_scen_custom(bundle, di, lookback)
        nscen.append(len(w))
        N_scen = (ls - ps).reshape(len(w), -1)
        N_plan = np.zeros((h, SLOTS))
        for k in range(h):
            kk = di + k if di + k < ND else di
            N_plan[k] = bundle.load_kwh[kk, 0] - bundle.pv_kwh[kk, 0]
        prices = np.tile(price, h)
        plan = solve_horizon(N_plan.reshape(-1), N_scen, w, e_state, h, True)
        al = data.load_kw[di] * DT_HOURS
        ap = data.pv_kw[di] * DT_HOURS
        ex = execute_day(plan, al, ap, price, e_state)
        tp += float(ex["planned_cost_yuan"].sum())
        te += float(ex["emergency_cost_yuan"].sum())
        tc += float(ex["surplus_kwh"].sum())
        e_state = float(ex["energy_end_kwh"][-1])
    return tp, te, tc, float(np.mean(nscen)), min(nscen)


print("=" * 76)
print("定位差距：48h + 不等式 + 周期终端，改变场景窗口")
print("=" * 76)
for lb, desc in [(28, "S1 窗口 28 天（我方旧）"), (56, "S2 窗口 56 天（C_yang 新版）"),
                 (90, "S3 窗口 90 天"), (112, "S4 窗口 112 天")]:
    pc, ec, cur, avg_s, min_s = run(2, lb)
    print(f"{desc}: 计划费={pc/1e4:>8.1f}万 紧急费={ec/1e4:>7.1f}万 "
          f"总={(pc+ec)/1e4:>8.1f}万 弃电={cur/1e4:.1f}万kWh 场景数均{avg_s:.1f}/最少{min_s}")
print()
print("对照: C_yang 最新版 1438.9 万（窗口 56 天 + 漂移校正预测）")
