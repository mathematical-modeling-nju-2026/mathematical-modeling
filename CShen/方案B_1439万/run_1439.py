"""问题2 最优方案（1438.9 万）独立复现脚本。

方案构成（五件套，缺一不可）
  ① 预测器   : L[sw4/d5] + V[t7/d28]  —— 同星期几均值 + 漂移校正
  ② 计划平衡 : 不等式 g + d - c >= N̂（保留报童自由空间）
  ③ 时域终端 : 48h 滚动前瞻 + 周期终端（末段电量 = 起点电量）
  ④ 场景     : 最近 56 天整日联合残差，等权不削减
  ⑤ 结构     : 两阶段随机规划（计划非前瞻，紧急购电场景补救）

理论支撑：报童临界分位 F* = 1 - 1/5 = 0.80

依赖
  - 本仓库 C_yang/q2/ 的 q2_data.py（数据层）
  - 本机 math-modeling-skill/output/c2026_q2/opt_v3/ 的 forecaster（预测器）

输出（本脚本所在目录）
  result2.xlsx            三个工作表：计划购电量 / 充放电量 / 紧急购电量
  daily_summary.csv       逐日结算
  schedule_detail.csv     逐时段明细
  summary.json            汇总指标
  verification.json       可行性校验
  figures/fig1..fig5      论文图表
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
# --- 依赖路径（相对本仓库；若目录移动请修改） ---
REPO = HERE.parents[1]                                   # mathematical-modeling/
CY = REPO / "C_yang" / "q2"
OPT_V3 = REPO.parent / "math-modeling-skill" / "output" / "c2026_q2" / "opt_v3"
sys.path.insert(0, str(CY))

from q2_data import DT, T, load_attachment1, load_attachment2, net_load, template_labels  # noqa: E402

# ============================ 配置 ============================
HORIZON = 2              # 前瞻天数
WINDOW = 56              # 场景窗口（天）
REPORT_FROM = 31         # 2025-02-01（0-based）
E_INIT, E_MIN, E_MAX = 6000.0, 1200.0, 10800.0
ETA_C = ETA_D = 0.90
P_MAX = 5000.0
FLOW_CAP = P_MAX * DT
EMERGENCY_MULT = 5.0
YEAR_END_E = E_INIT
# 预测器：负载用最近 4 次同星期几均值 + 近 5 天误差校正；光伏用近 7 天均值 + 近 28 天误差校正
LOAD_K, LOAD_DRIFT = 4, 5
PV_M, PV_DRIFT = 7, 28


# ======================== ① 预测器 ========================
def _sw(X, d, k, upto=None):
    """最近 k 次同星期几的均值。"""
    idx = [d - 7 * j for j in range(1, k + 1)
           if d - 7 * j >= 0 and (upto is None or d - 7 * j < upto)]
    return X[idx].mean(axis=0) if idx else None


def _tr(X, d, m, upto=None):
    """最近 m 天均值。"""
    hi = d if upto is None else min(d, upto)
    return X[max(0, hi - m):hi].mean(axis=0) if hi > 0 else None


def _channel(X, d, kernel, drift, upto=None):
    """带漂移校正的预测通道：raw + 近 drift 天平均误差。"""
    raw = kernel(X, d, upto)
    if raw is None:
        return None
    if drift == 0:
        return raw
    hi = d if upto is None else min(d, upto)
    errs = []
    for dd in range(max(0, hi - drift), hi):
        r = kernel(X, dd, upto)
        if r is not None:
            errs.append(X[dd] - r)
    return raw if not errs else raw + np.mean(errs, axis=0)


def forecast_net(L, V, d, upto=None):
    """净负载点预测（kW）：负载通道 - 光伏通道。"""
    fl = _channel(L, d, lambda X, dd, up: _sw(X, dd, LOAD_K, up), LOAD_DRIFT, upto)
    fv = _channel(V, d, lambda X, dd, up: _tr(X, dd, PV_M, up), PV_DRIFT, upto)
    _, _, l1, v1 = load_attachment1()
    fl = l1 if fl is None else fl
    fv = v1 if fv is None else fv
    return fl - fv


def residual_matrix(L, V):
    """历史整日残差（kW），预热期为 NaN：R[d] = N[d]*DT - 预测(d)。"""
    N = net_load(L, V)
    R = np.full((L.shape[0], T), np.nan)
    for d in range(L.shape[0]):
        pred = forecast_net(L, V, d)
        R[d] = N[d] - pred
    return R


def point_matrix(L, V):
    """逐日点预测矩阵（kWh）。"""
    N = net_load(L, V)
    FC = np.zeros((L.shape[0], T))
    for d in range(L.shape[0]):
        FC[d] = forecast_net(L, V, d) * DT
    return FC, N


# ======================== ② 单时段模型 ========================
def solve_horizon(N_plan, N_scen, weights, price, E_init, E_term):
    """滚动前瞻两阶段随机规划（稀疏 LP）。

    N_plan (K,)  计划用净负载点预测 kWh；K = H*T
    N_scen (S,T) 决策日场景净负载 kWh
    price  (K,)  电价
    E_term       终端电量（周期终端传 E_init；年末传 6000）
    """
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix

    K = N_plan.shape[0]
    S, TD = N_scen.shape
    n = 4 * K + S * TD
    G, C, D, E = slice(0, K), slice(K, 2 * K), slice(2 * K, 3 * K), slice(3 * K, 4 * K)
    EE = slice(4 * K, 4 * K + S * TD)

    # 目标
    c_obj = np.zeros(n)
    c_obj[G] = price
    px = price[:T]
    for s in range(S):
        c_obj[EE.start + s * T: EE.start + (s + 1) * T] = EMERGENCY_MULT * weights[s] * px

    # 等式：电量递推 + 终端
    rows, cols, vals, b_eq = [], [], [], []
    n_eq = K + 1
    b_eq = np.zeros(n_eq)
    for k in range(K):
        pairs = [(E.start + k, 1.0), (C.start + k, -ETA_C), (D.start + k, 1.0 / ETA_D)]
        if k > 0:
            pairs.append((E.start + k - 1, -1.0))
        else:
            b_eq[k] = E_init
        for j, v in pairs:
            rows.append(k); cols.append(j); vals.append(v)
    rows.append(K); cols.append(E.start + K - 1); vals.append(1.0); b_eq[K] = E_term
    A_eq = coo_matrix((vals, (rows, cols)), shape=(n_eq, n)).tocsr()

    # 不等式：计划下界（不等式）+ 场景平衡
    r2, c2, v2, b_list = [], [], [], []
    nrow = 0
    for k in range(K):
        r2 += [nrow] * 3; c2 += [G.start + k, D.start + k, C.start + k]
        v2 += [-1.0, -1.0, 1.0]; b_list.append(-N_plan[k]); nrow += 1
    for s in range(S):
        base = EE.start + s * T
        for t in range(T):
            r2 += [nrow] * 4; c2 += [base + t, G.start + t, D.start + t, C.start + t]
            v2 += [-1.0, -1.0, -1.0, 1.0]; b_list.append(-N_scen[s, t]); nrow += 1
    A_ub = coo_matrix((v2, (r2, c2)), shape=(nrow, n)).tocsr()
    b_ub = np.array(b_list)

    lb = np.zeros(n); ub = np.full(n, np.inf)
    lb[E], ub[E] = E_MIN, E_MAX
    ub[C] = FLOW_CAP; ub[D] = FLOW_CAP

    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=list(zip(lb, ub)), method="highs")
    if res.status != 0:
        raise RuntimeError(f"LP 失败: {res.message}")
    x = res.x
    g, c, d = x[G], x[C], x[D]
    # 精确消除同时充放电
    eff = ETA_C * ETA_D
    eps = np.minimum(c, d / eff)
    c = c - eps; d = d - eff * eps
    c[np.abs(c) < 1e-9] = 0.0; d[np.abs(d) < 1e-9] = 0.0
    return dict(g=g, c=c, d=d, z=g + d - c, E=x[E])


def settle_day(g, c, d, N_actual_kwh, price):
    """按题面结算：计划购电按 p 计费，缺口按 5p 紧急购电。"""
    z = g + d - c
    e = np.maximum(N_actual_kwh - z, 0.0)
    return dict(e=e,
                plan_cost=float(price @ g),
                emergency_cost=float(EMERGENCY_MULT * (price @ e)))


# ============================ 主流程 ============================
def main():
    _, L, V = load_attachment2()
    _, price, _, _ = load_attachment1()
    N = net_load(L, V)
    FC, _ = point_matrix(L, V)
    R = residual_matrix(L, V)

    ND = L.shape[0]
    g_arr = np.zeros((ND, T)); c_arr = np.zeros((ND, T)); d_arr = np.zeros((ND, T))
    z_arr = np.zeros((ND, T)); e_arr = np.zeros((ND, T)); Etraj = np.zeros((ND, T))
    E_start = np.zeros(ND); E_end = np.zeros(ND)
    plan_cost = np.zeros(ND); emg_cost = np.zeros(ND)

    E_now = E_INIT
    for d in range(ND):
        H = min(HORIZON, ND - d)
        # 前瞻点预测：只用第 0..d-1 天信息（upto=d）
        N_plan = np.concatenate([forecast_net(L, V, j, upto=d) * DT for j in range(d, d + H)])
        # 决策日场景：最近 WINDOW 天的有效残差
        lo = max(0, d - WINDOW)
        Rw = R[lo:d]
        ok = ~np.isnan(Rw).any(axis=1)
        Rw = Rw[ok]
        if Rw.shape[0] == 0:
            Rw = np.zeros((1, T))
        N_scen = FC[d][None, :] + Rw * DT
        w = np.full(Rw.shape[0], 1.0 / Rw.shape[0])
        # 终端：年末回 6000，其余周期终端
        E_term = YEAR_END_E if d == ND - 1 else E_now
        plan = solve_horizon(N_plan, N_scen, w, np.tile(price, H), E_now, E_term)

        g0, c0, d0 = plan["g"][:T], plan["c"][:T], plan["d"][:T]
        g_arr[d], c_arr[d], d_arr[d], z_arr[d] = g0, c0, d0, g0 + d0 - c0
        E_start[d] = E_now
        Etraj[d] = plan["E"][:T]
        E_now = float(plan["E"][T - 1])
        E_end[d] = E_now

        st = settle_day(g0, c0, d0, N[d] * DT, price)
        e_arr[d] = st["e"]
        plan_cost[d] = st["plan_cost"]
        emg_cost[d] = st["emergency_cost"]
        if d % 30 == 0 or d == ND - 1:
            print(f"  第 {d+1:3d}/{ND} 天  E={E_now:8.2f}  累计费用="
                  f"{(plan_cost[REPORT_FROM:d+1].sum()+emg_cost[REPORT_FROM:d+1].sum())/1e4:8.2f} 万",
                  flush=True)

    i0 = REPORT_FROM
    sl = slice(i0, ND)
    tot_plan = float(plan_cost[sl].sum())
    tot_emg = float(emg_cost[sl].sum())
    total = tot_plan + tot_emg
    dates = [datetime(2025, 1, 1).replace(year=2025) for _ in range(ND)]
    from datetime import timedelta
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(ND)]

    # ---------------- 校验 ----------------
    E_traj_rep = Etraj[sl]
    checks = {
        "report_days": int(ND - i0),
        "energy_min_kwh": float(E_traj_rep.min()),
        "energy_max_kwh": float(E_traj_rep.max()),
        "charge_max_kwh_per_slot": float(c_arr[sl].max()),
        "discharge_max_kwh_per_slot": float(d_arr[sl].max()),
        "flow_cap_kwh_per_slot": FLOW_CAP,
        "grid_nonneg": bool((g_arr[sl] >= -1e-7).all()),
        "simultaneous_charge_discharge_periods": int(
            ((c_arr[sl] > 1e-6) & (d_arr[sl] > 1e-6)).sum()),
        "plan_supply_ge_forecast_min_margin": float(
            np.min(z_arr[sl] - np.array([forecast_net(L, V, d) * DT for d in range(i0, ND)]))),
        "emergency_equals_deficit_max_dev": float(
            np.abs(e_arr[sl] - np.maximum(N[sl] * DT - z_arr[sl], 0)).max()),
        "cross_day_continuity_max_dev": float(np.abs(E_end[i0:ND-1] - E_start[i0+1:ND]).max()),
        "year_end_energy_kwh": float(E_end[-1]),
    }
    checks["pass"] = bool(
        checks["energy_min_kwh"] >= E_MIN - 1e-6
        and checks["energy_max_kwh"] <= E_MAX + 1e-6
        and checks["charge_max_kwh_per_slot"] <= FLOW_CAP + 1e-6
        and checks["discharge_max_kwh_per_slot"] <= FLOW_CAP + 1e-6
        and checks["grid_nonneg"]
        and checks["simultaneous_charge_discharge_periods"] == 0
        and checks["cross_day_continuity_max_dev"] <= 1e-6
        and abs(checks["year_end_energy_kwh"] - YEAR_END_E) <= 1e-6
    )

    # ---------------- 汇总 ----------------
    emg_periods = int((e_arr[sl] > 1e-6).sum())
    dump = float(np.maximum(z_arr[sl] - N[sl] * DT, 0).sum())
    summary = {
        "scheme": "1439万方案（48h前瞻 + 不等式 + 周期终端 + 漂移校正预测）",
        "report_period": [dates[i0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")],
        "days": int(ND - i0),
        "total_cost_yuan": total,
        "total_cost_wan": total / 1e4,
        "planned_cost_yuan": tot_plan,
        "emergency_cost_yuan": tot_emg,
        "emergency_kwh": float(e_arr[sl].sum()),
        "planned_grid_kwh": float(g_arr[sl].sum()),
        "charge_kwh": float(c_arr[sl].sum()),
        "discharge_kwh": float(d_arr[sl].sum()),
        "dump_kwh": dump,
        "dump_ratio_of_plan": float(dump / max(g_arr[sl].sum(), 1e-9)),
        "emergency_periods": emg_periods,
        "emergency_period_fraction": emg_periods / float((ND - i0) * T),
        "emergency_days": int((e_arr[sl].sum(axis=1) > 1e-6).sum()),
        "energy_initial_kwh": float(E_start[i0]),
        "energy_final_kwh": float(E_end[-1]),
        "config": {"horizon": HORIZON, "window": WINDOW,
                   "load_kernel": f"sw{LOAD_K}/drift{LOAD_DRIFT}",
                   "pv_kernel": f"t{PV_M}/drift{PV_DRIFT}",
                   "emergency_multiplier": EMERGENCY_MULT,
                   "newsboy_fractile": 1 - 1 / EMERGENCY_MULT},
    }

    print()
    print("=" * 64)
    print(f"结果期 {summary['report_period'][0]} ~ {summary['report_period'][1]}")
    print(f"  计划购电费 : {tot_plan:,.2f} 元")
    print(f"  紧急购电费 : {tot_emg:,.2f} 元")
    print(f"  总购电费   : {total:,.2f} 元  ({total/1e4:.1f} 万)")
    print(f"  紧急购电量 : {summary['emergency_kwh']:,.2f} kWh")
    print(f"  弃置电量   : {dump:,.2f} kWh")
    print(f"  校验通过   : {checks['pass']}")

    # ---------------- 导出 result2.xlsx ----------------
    export_result2(g_arr[sl], c_arr[sl], d_arr[sl], E_start[sl], E_end[sl],
                   e_arr[sl], dates[i0:], HERE / "result2.xlsx", price, plan_cost[sl])
    export_daily_csv(g_arr[sl], e_arr[sl], plan_cost[sl], emg_cost[sl],
                     E_start[sl], E_end[sl], c_arr[sl], d_arr[sl],
                     z_arr[sl], N[sl], dates[i0:], HERE / "daily_summary.csv")
    export_detail_csv(g_arr[sl], c_arr[sl], d_arr[sl], z_arr[sl], FC[sl],
                      e_arr[sl], E_end[sl], dates[i0:], HERE / "schedule_detail.csv")
    (HERE / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "verification.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- 图表 ----------------
    try:
        from make_figures_B import make_all_figures
        make_all_figures(HERE, g_arr[sl], e_arr[sl], c_arr[sl], d_arr[sl],
                         z_arr[sl], Etraj[sl], E_start[sl], E_end[sl],
                         plan_cost[sl], emg_cost[sl], N[sl], FC[sl],
                         price, dates[i0:], summary, R, L, V)
        print("  图表已生成: figures/")
    except Exception as ex:      # 绘图失败不影响数值结果
        print(f"  [警告] 绘图失败: {ex}")

    print(f"\n输出目录: {HERE}")


# ------------------------ 导出辅助 ------------------------
def export_result2(g, c, d, E_start, E_end, e, dates, path, price, plan_cost):
    """result2.xlsx（修复版：充放电时段按 24 段/4 小时切分）。"""
    import openpyxl
    from openpyxl.styles import Font, Alignment

    labels = template_labels()
    wb = openpyxl.Workbook()
    bold = Font(bold=True)

    ws = wb.active; ws.title = "计划购电量"
    ws.append(["日期\\时间"] + labels + ["全天购电量", "全天购电费"])
    for cc in ws[1]:
        cc.font = bold; cc.alignment = Alignment(horizontal="center")
    for i, dt in enumerate(dates):
        ws.append([dt] + [round(float(v), 4) for v in g[i]] +
                  [round(float(g[i].sum()), 4), round(float(plan_cost[i]), 2)])
    ws.column_dimensions["A"].width = 12
    ws.freeze_panes = "B2"

    ws2 = wb.create_sheet("充放电量")
    ws2.append(["日期", "时间段", "充电量", "放电量", "时刻", "储电量"])
    for cc in ws2[1]:
        cc.font = bold
    blocks = ["0:00-4:00", "4:00-8:00", "8:00-12:00",
              "12:00-16:00", "16:00-20:00", "20:00-24:00"]
    for i, dt in enumerate(dates):
        for b, nm in enumerate(blocks):
            t0, t1 = b * 24, (b + 1) * 24          # ← 修复：原为 b*36
            ws2.append([dt if b == 0 else None, nm,
                        round(float(c[i, t0:t1].sum()), 4),
                        round(float(d[i, t0:t1].sum()), 4),
                        time(0, 0) if b == 0 else ("24:00" if b == 1 else None),
                        round(float(E_start[i]), 4) if b == 0
                        else (round(float(E_end[i]), 4) if b == 1 else None)])
    for col, wd in zip("ABCDEF", (12, 14, 12, 12, 10, 12)):
        ws2.column_dimensions[col].width = wd

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


def _lbl(t):
    m = t * 10
    return "0:00+1" if m == 1440 else f"{m // 60:02d}:{m % 60:02d}"


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
    # 区间标签用"起点-终点"
    return [(_lbl_hm(a), _lbl_hm(b), q) for a, b, q in out]


def _lbl_hm(t):
    m = t * 10
    return "0:00+1" if m >= 1440 else f"{m // 60}:{m % 60:02d}"


def export_daily_csv(g, e, plan_cost, emg_cost, E_start, E_end, c, d, z, N,
                     dates, path):
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "计划购电量kWh", "紧急购电量kWh", "计划购电费元",
                    "紧急购电费元", "合计购电费元", "紧急时段数",
                    "0:00储电量kWh", "24:00储电量kWh", "充电量kWh", "放电量kWh",
                    "计划净供给kWh", "弃置电量kWh"])
        for i, dt in enumerate(dates):
            w.writerow([dt.strftime("%Y-%m-%d"),
                        f"{g[i].sum():.4f}", f"{e[i].sum():.4f}",
                        f"{plan_cost[i]:.2f}", f"{emg_cost[i]:.2f}",
                        f"{plan_cost[i]+emg_cost[i]:.2f}",
                        int(np.sum(e[i] > 1e-6)),
                        f"{E_start[i]:.4f}", f"{E_end[i]:.4f}",
                        f"{c[i].sum():.4f}", f"{d[i].sum():.4f}",
                        f"{z[i].sum():.4f}",
                        f"{max(z[i].sum() - N[i].sum()*DT, 0):.4f}"])


def export_detail_csv(g, c, d, z, fc, e, E_end, dates, path):
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "时段", "计划购电量kWh", "充电量kWh", "放电量kWh",
                    "计划净供给kWh", "净负载预测kWh", "紧急购电量kWh"])
        for i, dt in enumerate(dates):
            for t in range(T):
                w.writerow([dt.strftime("%Y-%m-%d"), _lbl_hm(t + 1),
                            f"{g[i,t]:.4f}", f"{c[i,t]:.4f}", f"{d[i,t]:.4f}",
                            f"{z[i,t]:.4f}", f"{fc[i,t]:.4f}", f"{e[i,t]:.4f}"])


if __name__ == "__main__":
    main()
