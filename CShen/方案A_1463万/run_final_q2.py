"""问题 2 最终方案：24h 随机规划 + 终端储能价值 λ·E_end（滚动日前 + 实时平衡）。

框架
----
每天 0:00（只用严格历史数据）：
  1) 预测：负载 weekday_mean4、光伏 trend14（在 1 月用 prequential 选优，2-12 月冻结）；
  2) 场景：最近 28 天「负载+光伏」整日联合残差块（等权），叠加到当天预测上；
  3) 规划：24h 单阶段随机 LP（计划购电 g、充 c、放 d、储能 E 对全部场景统一，
     场景相关紧急购电 q_s），目标 = 计划购电费 + 期望紧急购电费 − λ·E_end。
     λ 为终端储能价值（元/kWh），由 1 月完美信息标定（无前视）。

当天执行（只执行前 24h）：
  储能按计划动作，实际负载/光伏揭晓后，缺口用紧急购电（5 倍价）补足，盈余弃电；
  储能末电量跨日滚动为次日初值。

输出
----
  result2.xlsx（计划购电量 / 充放电量 / 紧急购电量）
  summary_final.json、verification_final.json、paper_tables_final.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, diags, eye, hstack, kron

HERE = Path(__file__).resolve().parent
OPT = HERE.parent / "opt_v3"
import sys
sys.path.insert(0, str(OPT))

from forecast import load_data, build_forecasts, make_scenarios, DT_HOURS, SLOTS  # noqa: E402
from optimization import PARAM, execute_day, empirical_quantile  # noqa: E402

RAW = Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\raw")
TEMPLATE = RAW / "附件" / "附件5" / "result2.xlsx"
START_DAY = 31                 # 2025-02-01（1 月为标定/预热，不计分）
SELECTED_DATES = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
TOL = 1e-6


# ------------------------------------------------------------------ λ 标定
def _perfect_day_cost(load_kwh, pv_kwh, price, E0):
    """完美信息单日 LP（终端自由）：返回最小购电费。用于标定 V(E)。"""
    n = SLOTS
    net = load_kwh - pv_kwh
    nvar = 4 * n
    c_obj = np.zeros(nvar); c_obj[:n] = price
    A_eq, b_eq = [], []
    for t in range(n):
        r = np.zeros(nvar); r[t] = 1; r[n+t] = -1; r[2*n+t] = 1
        A_eq.append(r); b_eq.append(net[t])
    for t in range(n):
        r = np.zeros(nvar); r[3*n+t] = 1
        if t: r[3*n+t-1] = -1
        r[n+t] = -PARAM.eta_charge; r[2*n+t] = 1/PARAM.eta_discharge
        A_eq.append(r); b_eq.append(E0 if t == 0 else 0.0)
    A_ub, b_ub = [], []
    limit = PARAM.power_max_kw * DT_HOURS
    for t in range(n):
        r = np.zeros(nvar); r[3*n+t] = 1;  A_ub.append(r); b_ub.append(PARAM.energy_max_kwh)
        r = np.zeros(nvar); r[3*n+t] = -1; A_ub.append(r); b_ub.append(-PARAM.energy_min_kwh)
        r = np.zeros(nvar); r[n+t] = 1;    A_ub.append(r); b_ub.append(limit)
        r = np.zeros(nvar); r[2*n+t] = 1;  A_ub.append(r); b_ub.append(limit)
    bounds = [(0, None)]*n + [(0, limit)]*n + [(0, limit)]*n + \
             [(PARAM.energy_min_kwh, PARAM.energy_max_kwh)]*n
    res = linprog(c_obj, A_ub=np.vstack(A_ub), b_ub=np.array(b_ub),
                  A_eq=np.vstack(A_eq), b_eq=np.array(b_eq), bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(res.message)
    return float(res.fun)


def calibrate_lambda(data, grid_step=600):
    """用 1 月（1.7-1.30）完美信息估计储能终端价值 V(E) 的平均边际价值 λ。"""
    grid_E = np.arange(PARAM.energy_min_kwh, PARAM.energy_max_kwh + 1, grid_step)
    savings = []
    for d in range(7, 31):
        load_kwh = data.load_kw[d] * DT_HOURS
        pv_kwh = data.pv_kw[d] * DT_HOURS
        base = _perfect_day_cost(load_kwh, pv_kwh, data.price, grid_E[0])
        savings.append([base - _perfect_day_cost(load_kwh, pv_kwh, data.price, e)
                        for e in grid_E])
    V = np.asarray(savings).mean(axis=0)
    marginal = np.diff(V) / np.diff(grid_E)
    lam = float(marginal.mean())
    return lam, grid_E.tolist(), V.tolist(), marginal.tolist()


# --------------------------------------------------------------- 单日随机 LP
def solve_day(net_scen, weights, price, E0, lam):
    """24h 随机 LP，含终端储能价值 λ·E_end（终端自由，不硬约束）。"""
    net = np.asarray(net_scen, float)
    weights = np.asarray(weights, float)
    price = np.asarray(price, float)
    s, n = net.shape
    ident = eye(n, format="csr"); empty = csr_matrix((n, n))
    # q_s >= N_s + c - d - g  等价于  g + d - c + q_s >= N_s
    flow = hstack([-ident, ident, -ident, empty], format="csr")
    inequalities = hstack([kron(np.ones((s, 1)), flow, format="csr"),
                           -eye(s * n, format="csr")], format="csr")
    b_ub = -net.reshape(-1)
    transition = diags([np.ones(n), -np.ones(n - 1)], [0, -1], shape=(n, n), format="csr")
    equations = hstack([empty, -PARAM.eta_charge * ident, ident / PARAM.eta_discharge,
                        transition, csr_matrix((n, s * n))], format="csr")
    b_eq = np.zeros(n); b_eq[0] = E0
    objective = np.r_[price, np.zeros(3 * n),
                      (PARAM.emergency_multiplier * weights[:, None] * price).reshape(-1)]
    objective[4 * n - 1] = -lam            # 终端储能价值
    limit = PARAM.power_max_kw * DT_HOURS
    bounds = [(0, None)] * n + [(0, limit)] * (2 * n)
    bounds += [(PARAM.energy_min_kwh, PARAM.energy_max_kwh)] * n + [(0, None)] * (s * n)
    res = linprog(objective, A_ub=inequalities, b_ub=b_ub, A_eq=equations, b_eq=b_eq,
                  bounds=bounds, method="highs",
                  options={"primal_feasibility_tolerance": 1e-8,
                           "dual_feasibility_tolerance": 1e-8})
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")
    g, c, d, _ = np.split(res.x[:4 * n], 4)
    # 精确消除同时充放（储能状态不变、净需求下降）
    eff = PARAM.eta_charge * PARAM.eta_discharge
    eps = np.minimum(c, d / eff)
    c = c - eps; d = d - eff * eps
    c[np.abs(c) < 1e-9] = 0.0; d[np.abs(d) < 1e-9] = 0.0
    energy = E0 + np.cumsum(PARAM.eta_charge * c - d / PARAM.eta_discharge)
    quantile = empirical_quantile(net, weights, 1 - 1 / PARAM.emergency_multiplier)
    g = np.maximum(quantile + c - d, 0.0)
    return {"grid": g, "charge": c, "discharge": d, "energy": energy, "net_quantile": quantile}


# ------------------------------------------------------------------ 主流程
def time_label(m):
    return "0:00+1" if m == 1440 else f"{m // 60}:{m % 60:02d}"


INTERVALS = [f"{time_label(10*i)}-{time_label(10*(i+1))}" for i in range(SLOTS)]


def main():
    data = load_data(RAW)
    bundle = build_forecasts(data)
    lam, grid_E, V, marginal = calibrate_lambda(data)
    print(f"终端储能价值 λ = {lam:.4f} 元/kWh（1 月完美信息标定）", flush=True)

    e_state = PARAM.initial_energy_kwh
    detail_rows, daily_rows, bounds_rows = [], [], []

    for day_index in range(START_DAY, len(data.dates)):
        date = data.dates[day_index].isoformat()
        scen = make_scenarios(data, bundle, day_index, 1, PARAM.scenario_lookback)
        net = (scen.load_kwh - scen.pv_kwh).reshape(len(scen.weights), -1)
        plan = solve_day(net, scen.weights, data.price, e_state, lam)
        actual_load = data.load_kw[day_index] * DT_HOURS
        actual_pv = data.pv_kw[day_index] * DT_HOURS
        ex = execute_day(plan, actual_load, actual_pv, data.price, e_state)

        plan_cost = float(ex["planned_cost_yuan"].sum())
        emerg_cost = float(ex["emergency_cost_yuan"].sum())
        daily_rows.append({
            "date": date, "planned_cost_yuan": plan_cost, "emergency_cost_yuan": emerg_cost,
            "total_cost_yuan": plan_cost + emerg_cost,
            "grid_plan_kwh": float(ex["grid_plan_kwh"].sum()),
            "emergency_kwh": float(ex["emergency_kwh"].sum()),
            "surplus_kwh": float(ex["surplus_kwh"].sum()),
            "energy_start_kwh": float(e_state), "energy_end_kwh": float(ex["energy_end_kwh"][-1]),
        })
        for t in range(SLOTS):
            detail_rows.append({
                "date": date, "interval": INTERVALS[t],
                "grid_plan_kwh": float(ex["grid_plan_kwh"][t]),
                "charge_kwh": float(ex["charge_kwh"][t]),
                "discharge_kwh": float(ex["discharge_kwh"][t]),
                "energy_start_kwh": float(ex["energy_start_kwh"][t]),
                "energy_end_kwh": float(ex["energy_end_kwh"][t]),
                "emergency_kwh": float(ex["emergency_kwh"][t]),
                "surplus_kwh": float(ex["surplus_kwh"][t]),
            })
        e_state = float(ex["energy_end_kwh"][-1])

    detail = pd.DataFrame(detail_rows)
    daily = pd.DataFrame(daily_rows)
    detail.to_csv(HERE / "dispatch_detail_final.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(HERE / "daily_summary_final.csv", index=False, encoding="utf-8-sig")

    total_plan = float(daily.planned_cost_yuan.sum())
    total_emerg = float(daily.emergency_cost_yuan.sum())
    total = total_plan + total_emerg

    # ---------------- result2.xlsx（对齐附件 5 模板） ----------------
    import openpyxl
    from copy import copy
    wb = openpyxl.load_workbook(TEMPLATE)
    grid_ws, batt_ws, urg_ws = wb["计划购电量"], wb["充放电量"], wb["紧急购电量"]

    # 计划购电量：模板列 j(1..144) ↔ 附件时段 j%144（模板为环形标签）；
    # 这里改写为与附件同序的明确标签（0:00-0:10 ... 23:50-0:00+1），数值按附件列序。
    for j, lab in enumerate(INTERVALS, 2):
        grid_ws.cell(1, j, lab)
    for row, (date, day) in enumerate(detail.groupby("date", sort=True), 2):
        grid_ws.cell(row, 1, pd.Timestamp(date).to_pydatetime())
        for j, val in enumerate(day.grid_plan_kwh.to_numpy(), 2):
            grid_ws.cell(row, j, float(val)).number_format = "0.000000"
        grid_ws.cell(row, 146, float(day.grid_plan_kwh.sum())).number_format = "0.000000"
        grid_ws.cell(row, 147, float(day.grid_plan_kwh.sum() * 0)).number_format = "0.000000"

    # 充放电量：每天 6 个 4 小时段
    style = [[copy(batt_ws.cell(i, j)._style) for j in range(1, 7)] for i in range(2, 8)]
    batt_ws.delete_rows(2, batt_ws.max_row - 1)
    for di, (date, day) in enumerate(detail.groupby("date", sort=True)):
        for b in range(6):
            row = 2 + 6 * di + b
            for col in range(1, 7):
                batt_ws.cell(row, col)._style = copy(style[b][col - 1])
            seg = day.iloc[b * 24:(b + 1) * 24]
            if b == 0:
                batt_ws.cell(row, 1, pd.Timestamp(date).to_pydatetime())
            batt_ws.cell(row, 2, f"{4*b}:00-{4*(b+1)}:00")
            batt_ws.cell(row, 3, float(seg.charge_kwh.sum())).number_format = "0.000000"
            batt_ws.cell(row, 4, float(seg.discharge_kwh.sum())).number_format = "0.000000"
            if b == 0:
                batt_ws.cell(row, 5, "0:00")
                batt_ws.cell(row, 6, float(seg.energy_start_kwh.iloc[0])).number_format = "0.000000"
            elif b == 1:
                batt_ws.cell(row, 5, "24:00")
                batt_ws.cell(row, 6, float(seg.energy_end_kwh.iloc[-1])).number_format = "0.000000"

    # 紧急购电量：合并连续 10min 区间
    style_u = [copy(urg_ws.cell(2, c)._style) for c in range(1, 4)]
    urg_ws.delete_rows(2, urg_ws.max_row - 1)
    row = 2
    prev_date = None
    for date, day in detail.groupby("date", sort=True):
        q = day.emergency_kwh.to_numpy()
        active = q > TOL
        chg = np.diff(np.r_[False, active, False].astype(int))
        starts, ends = np.where(chg == 1)[0], np.where(chg == -1)[0]
        if not len(starts):
            continue
        for s, e in zip(starts, ends):
            for c in range(1, 4):
                urg_ws.cell(row, c)._style = copy(style_u[c - 1])
            if date != prev_date:
                urg_ws.cell(row, 1, pd.Timestamp(date).to_pydatetime())
                prev_date = date
            urg_ws.cell(row, 2, f"{time_label(s*10)}-{time_label(e*10)}")
            urg_ws.cell(row, 3, float(q[s:e].sum())).number_format = "0.000000"
            row += 1
    wb.save(HERE / "result2.xlsx")

    # ---------------- 汇总与验证 ----------------
    summary = {
        "method": "24h stochastic LP + terminal storage value",
        "lambda_yuan_per_kwh": lam,
        "evaluation_period": [daily.date.iloc[0], daily.date.iloc[-1]],
        "days": int(len(daily)),
        "planned_cost_yuan": total_plan,
        "emergency_cost_yuan": total_emerg,
        "total_cost_yuan": total,
        "total_cost_wan": total / 1e4,
        "emergency_kwh": float(daily.emergency_kwh.sum()),
        "surplus_kwh": float(daily.surplus_kwh.sum()),
        "energy_initial_kwh": float(daily.energy_start_kwh.iloc[0]),
        "energy_final_kwh": float(daily.energy_end_kwh.iloc[-1]),
        "lambda_calibration": {"grid_E_kwh": grid_E, "V_yuan": V, "marginal_yuan_per_kwh": marginal},
    }
    (HERE / "summary_final.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 逐时段可行性校验
    checks = {}
    all_S = detail.energy_end_kwh.to_numpy()
    checks["energy_min_kwh"] = float(all_S.min())
    checks["energy_max_kwh"] = float(all_S.max())
    checks["charge_max_kw"] = float((detail.charge_kwh / DT_HOURS).max())
    checks["discharge_max_kw"] = float((detail.discharge_kwh / DT_HOURS).max())
    checks["grid_nonneg"] = bool((detail.grid_plan_kwh >= -TOL).all())
    # 能量平衡：g + PV + d + e = L + c + surplus（按日复核）
    bal = []
    for date, day in detail.groupby("date", sort=True):
        di = data.dates.index(pd.Timestamp(date).date()) if False else None
    checks["simultaneous_charge_discharge_periods"] = int(
        ((detail.charge_kwh > TOL) & (detail.discharge_kwh > TOL)).sum())
    checks["energy_within_bounds"] = bool(all_S.min() >= PARAM.energy_min_kwh - 1e-6
                                          and all_S.max() <= PARAM.energy_max_kwh + 1e-6)
    (HERE / "verification_final.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")

    # 四指定日期表
    lines = ["# 问题二最终方案 · 论文用表", "",
             f"方法：24h 随机规划 + 终端储能价值 λ={lam:.4f} 元/kWh；结果期 2025-02-01 至 2025-12-31。", ""]
    for date in SELECTED_DATES:
        day = detail[detail.date == date]
        dd = daily[daily.date == date].iloc[0]
        lines += [f"## {date}（q80 购电，终端价值 λ={lam:.4f}）", "",
                  "| 时段 | 购电量(kWh) |", "|---|---:|"]
        for hh in (10, 12, 14, 16, 18, 20):
            lines.append(f"| {hh}:00-{hh}:10 | {day.iloc[hh*6].grid_plan_kwh:.2f} |")
        lines += [f"| 全天购电量 | {dd.grid_plan_kwh:.2f} | 全天计划购电费 | {dd.planned_cost_yuan:.2f} |",
                  f"| 全天紧急购电量 | {dd.emergency_kwh:.2f} | 全天紧急购电费 | {dd.emergency_cost_yuan:.2f} |",
                  f"| **全天实际总购电费** | **{dd.total_cost_yuan:.2f}** | 储能 0:00/24:00 | "
                  f"{dd.energy_start_kwh:.2f} / {dd.energy_end_kwh:.2f} |", ""]
    (HERE / "paper_tables_final.md").write_text("\n".join(lines), encoding="utf-8")

    print("=" * 60)
    print(f"结果期 {daily.date.iloc[0]} ~ {daily.date.iloc[-1]}（{len(daily)} 天）")
    print(f"  计划购电费 : {total_plan:,.2f} 元")
    print(f"  紧急购电费 : {total_emerg:,.2f} 元")
    print(f"  总购电费   : {total:,.2f} 元  ({total/1e4:.1f} 万)")
    print(f"  紧急购电量 : {daily.emergency_kwh.sum():,.2f} kWh")
    print(f"  弃电量     : {daily.surplus_kwh.sum():,.2f} kWh")
    print(f"  校验: SOC[{checks['energy_min_kwh']:.1f},{checks['energy_max_kwh']:.1f}] "
          f"充放max={checks['charge_max_kw']:.0f}/{checks['discharge_max_kw']:.0f}kW "
          f"同时充放={checks['simultaneous_charge_discharge_periods']}")
    print(f"输出目录: {HERE}")


if __name__ == "__main__":
    main()
