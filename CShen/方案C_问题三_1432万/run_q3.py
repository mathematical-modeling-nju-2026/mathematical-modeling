"""问题3 主流程：日前计划 + 多时点调整（6/12/18）+ 储能执行 + 结算。

计费（题面）
  总费用 = 计划购电费 + 紧急购电费 + 调整购电量相关费用
  对每时段 t（计划 g_p、调整 g_a、电价 p、紧急 e）：
    cost_t = p*g_p + 1.5p*max(0,g_a-g_p) - 0.5p*max(0,g_p-g_a) + 5p*e
  即：调增部分按 1.5p；调减（违约）部分按 0.5p 退款（净省 0.5p）。

决策结构（滚动）
  0:00  → 用附件3 当日 0:00 预报（覆盖 0:00-24:00）制定全天计划 g_plan
  6:00  → 用 6:00 预报重优化 [6:00,24:00)，锁定 [6:00,12:00)
  12:00 → 用 12:00 预报重优化 [12:00,24:00)，锁定 [12:00,18:00)
  18:00 → 用 18:00 预报重优化 [18:00,24:00)，锁定 [18:00,24:00)
  执行：储能按锁定计划，实际净负载缺口用紧急购电补足
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "opt_v3"))

from q3_data import (load_price, load_actual, load_forecast, fc_to_10min,
                     T, DT, STAGE_HOUR)
from q3_model import (solve_plan_24h, solve_adjust_stage,
                      ETA, E_MIN, E_MAX, FLOW_CAP, EMG, VIOL_RATIO, EXCESS_RATIO)

# 负载预测器（沿用方案B：最近4次同星期几均值 + 近5天误差校正）
LOAD_K, LOAD_DRIFT = 4, 5
WINDOW_RESID = 28
START_DAY = 31          # 2025-02-01
E_INIT = 6000.0
E_YEAR_END = E_INIT
HORIZON = 2             # 计划前瞻天数（与方案B一致）


# ---------------- 负载预测（同方案B）----------------
def load_forecast_matrix(L):
    """逐日负载点预测（kW），(365,144)。"""
    n = L.shape[0]
    out = np.zeros((n, T))
    for d in range(n):
        idx = [d - 7 * j for j in range(1, LOAD_K + 1) if d - 7 * j >= 0]
        raw = L[idx].mean(axis=0) if idx else L[max(d - 1, 0)]
        errs = []
        for dd in range(max(0, d - LOAD_DRIFT), d):
            i2 = [dd - 7 * j for j in range(1, LOAD_K + 1) if dd - 7 * j >= 0]
            r = L[i2].mean(axis=0) if i2 else L[max(dd - 1, 0)]
            errs.append(L[dd] - r)
        out[d] = raw if not errs else raw + np.mean(errs, axis=0)
    return out


# ---------------- 场景构造 ----------------
def build_residuals(L, PV, FC, load_fc):
    """历史残差（kW）：负载残差 (365,144)，光伏分阶段残差 (365,4,144)。"""
    Lres = L - load_fc
    PVres = np.full((365, 4, T), np.nan)
    for d in range(min(len(FC), PV.shape[0])):
        for s in range(4):
            f = fc_to_10min(FC[d], s)
            ok = ~np.isnan(f)
            PVres[d, s, ok] = PV[d, ok] - f[ok]
    return Lres, PVres


def scenarios_for_stage(Lres, PVres, d, s, t0):
    """第 d 天阶段 s（覆盖时段 [t0,144)）的场景净负载（kW），形状 (n,T_rem)。"""
    lo = max(0, d - WINDOW_RESID)
    cand = []
    for j in range(lo, d):
        if np.isnan(PVres[j, s, t0:]).any():
            continue
        cand.append(j)
    if not cand:
        cand = list(range(lo, d))
    Ls, Ps = [], []
    for j in cand:
        Ls.append(Lres[j, t0:])
        Ps.append(PVres[j, s, t0:])
    return np.asarray(Ls), np.asarray(Ps), np.asarray(cand)


# ---------------- 主仿真 ----------------
def simulate(use_adjust=True, verbose=True, scen_mode="resid", max_day=None,
             adjust_stages=(1, 2, 3)):
    price = load_price()
    L, PV = load_actual()
    FC, _ = load_forecast()
    load_fc = load_forecast_matrix(L)
    Lres, PVres = build_residuals(L, PV, FC, load_fc)
    if scen_mode == "point":
        # 退化实验：调整场景 = 单一点预测（零残差），判定残差场景集是否有偏
        Lres_adj = np.zeros_like(Lres)
        PVres_adj = np.nan_to_num(PVres, nan=0.0)
    else:
        Lres_adj, PVres_adj = Lres, PVres
    perfect = (scen_mode == "perfect")   # 完美预见：调整场景 = 当日实际净负载
    N = L - PV

    ND = L.shape[0]
    ND_rep = ND - START_DAY

    g_plan = np.zeros((ND, T)); g_final = np.zeros((ND, T))
    c_fin = np.zeros((ND, T)); d_fin = np.zeros((ND, T)); z_fin = np.zeros((ND, T))
    e_arr = np.zeros((ND, T)); E_start = np.zeros(ND); E_end = np.zeros(ND)
    c_plan = np.zeros((ND, T)); d_plan = np.zeros((ND, T))
    cost_plan = np.zeros(ND); cost_dev = np.zeros(ND); cost_emg = np.zeros(ND)

    E_now = E_INIT
    nd_stop = ND if max_day is None else max_day + 1
    for d in range(nd_stop):
        E_day0 = E_now
        # ---------------- 阶段0：0:00 制定全天计划（HORIZON 天前瞻）----------------
        load_pt = load_fc[d]
        pv_fc = fc_to_10min(FC[d], 0)                     # 覆盖 [0,144)
        Ls, Ps, cand = scenarios_for_stage(Lres, PVres, d, 0, 0)
        if len(cand) == 0:
            Ls = np.zeros((1, T)); Ps = np.zeros((1, T)); cand = [0]
        N_scen = (load_pt[None, :] + Ls) - (np.nan_to_num(pv_fc)[None, :] + Ps)
        w = np.full(len(cand), 1.0 / len(cand))
        # HORIZON 天点预测（当日用附件3 当日0:00预报，次日用次日0:00预报）
        segs = []
        for j in range(d, min(d + HORIZON, ND)):
            pvj = np.nan_to_num(fc_to_10min(FC[j], 0))
            segs.append((load_fc[j] - pvj) * DT)
        while len(segs) < HORIZON:
            segs.append(segs[-1])
        N_plan = np.concatenate(segs)
        E_term = E_YEAR_END if d == ND - 1 else E_day0
        plan = solve_plan_24h(N_plan, N_scen * DT, w, price, E_day0, E_term)
        gp, cp, dp = plan["g"][:T], plan["c"][:T], plan["d"][:T]
        E_plan_end = float(plan["E"][T - 1])
        g_plan[d] = gp; c_plan[d] = cp; d_plan[d] = dp

        # ---------------- 阶段1-3：调整 ----------------
        gF = gp.copy(); cF = cp.copy(); dF = dp.copy()
        if use_adjust:
            stages_sorted = sorted(adjust_stages)
            # 执行 [0, 首个调整时刻) 按原计划
            t_first = stages_sorted[0] * 36
            E_cur = E_day0 + np.sum(ETA * cF[:t_first] - dF[:t_first] / ETA)
            for idx, s in enumerate(stages_sorted):
                t0 = s * 36
                if t0 >= T:
                    break
                t_next = stages_sorted[idx + 1] * 36 if idx + 1 < len(stages_sorted) else T
                if perfect:
                    # 完美预见：调整场景即当日实际净负载（单场景）
                    N_scen2 = (N[d, t0:] * DT).reshape(1, -1)
                else:
                    pv_fc_s = fc_to_10min(FC[d], s)[t0:]
                    Ls2, Ps2, cand2 = scenarios_for_stage(Lres_adj, PVres_adj, d, s, t0)
                    if len(cand2) == 0:
                        Ls2 = np.zeros((1, T - t0)); Ps2 = np.zeros((1, T - t0))
                    N_scen2 = ((load_pt[t0:][None, :] + Ls2)
                               - (np.nan_to_num(pv_fc_s)[None, :] + Ps2)) * DT
                w2 = np.full(N_scen2.shape[0], 1.0 / N_scen2.shape[0])
                adj = solve_adjust_stage(
                    price[t0:], N_scen2, w2, E_cur,
                    gp[t0:], cp[t0:], dp[t0:],
                    E_term=E_plan_end)
                # 用最新调整解覆盖整个剩余时段 [t0,144)（该解自洽、可行）
                gF[t0:] = adj["g_adj"]
                cF[t0:] = adj["c"]
                dF[t0:] = adj["d"]
                # 按"执行段" [t0, t_next) 推进 SOC
                E_cur = E_cur + np.sum(ETA * cF[t0:t_next] - dF[t0:t_next] / ETA)
        g_final[d] = gF; c_fin[d] = cF; d_fin[d] = dF

        # ---------------- 结算 ----------------
        z = g_final[d] + d_fin[d] - c_fin[d]
        z_fin[d] = z
        e = np.maximum(N[d] * DT - z, 0.0)
        e_arr[d] = e
        gp, ga = g_plan[d], g_final[d]
        u = np.maximum(ga - gp, 0.0)
        v = np.maximum(gp - ga, 0.0)
        cost_plan[d] = float(price @ gp)
        cost_dev[d] = float(EXCESS_RATIO * (price @ u) - VIOL_RATIO * (price @ v))
        cost_emg[d] = float(EMG * (price @ e))
        E_start[d] = E_day0
        E_end[d] = E_day0 + np.sum(ETA * cF - dF / ETA)
        E_now = E_end[d] if d < ND - 1 else E_YEAR_END
        if verbose and (d % 30 == 0 or d == ND - 1):
            tot = (cost_plan[START_DAY:d+1].sum() + cost_dev[START_DAY:d+1].sum()
                   + cost_emg[START_DAY:d+1].sum())
            print(f"  第 {d+1:3d}/{ND} 天  E={E_now:8.1f}  累计={tot/1e4:8.2f} 万", flush=True)

    sl = slice(START_DAY, ND)
    res = dict(
        g_plan=g_plan[sl], g_final=g_final[sl], c=c_fin[sl], d=d_fin[sl],
        z=z_fin[sl], e=e_arr[sl], E_start=E_start[sl], E_end=E_end[sl],
        N=N[sl], price=price, load_fc=load_fc[sl],
        cost_plan=cost_plan[sl], cost_dev=cost_dev[sl], cost_emg=cost_emg[sl],
        dates=[datetime(2025, 1, 1) + timedelta(days=i) for i in range(START_DAY, ND)],
        use_adjust=use_adjust,
    )
    return res


def summarize(res):
    tp = float(res["cost_plan"].sum())
    td = float(res["cost_dev"].sum())
    te = float(res["cost_emg"].sum())
    return dict(plan_cost=tp, dev_cost=td, emg_cost=te, total=tp + td + te,
                total_wan=(tp + td + te) / 1e4)


if __name__ == "__main__":
    print("=" * 66)
    print("问题3：方案A 不做调整（仅 0:00 计划）")
    print("=" * 66)
    rA = simulate(use_adjust=False, verbose=False)
    sA = summarize(rA)
    print(f"  计划费={sA['plan_cost']/1e4:.2f}万 调整费={sA['dev_cost']/1e4:.2f}万 "
          f"紧急费={sA['emg_cost']/1e4:.2f}万 总={sA['total_wan']:.2f}万")

    print()
    print("=" * 66)
    print("问题3：方案B 做调整（6:00 / 12:00 / 18:00）")
    print("=" * 66)
    rB = simulate(use_adjust=True, verbose=True)
    sB = summarize(rB)
    print(f"  计划费={sB['plan_cost']/1e4:.2f}万 调整费={sB['dev_cost']/1e4:.2f}万 "
          f"紧急费={sB['emg_cost']/1e4:.2f}万 总={sB['total_wan']:.2f}万")
    print()
    print(f"调整带来的节省: {(sA['total']-sB['total'])/1e4:.2f} 万元")

    np.savez(HERE / "_q3_result.npz",
             dates=np.array([d.strftime("%Y-%m-%d") for d in rB["dates"]]),
             g_plan=rB["g_plan"], g_final=rB["g_final"], c=rB["c"], d=rB["d"],
             z=rB["z"], e=rB["e"], E_start=rB["E_start"], E_end=rB["E_end"],
             N=rB["N"], price=rB["price"])
    (HERE / "_q3_summary.json").write_text(json.dumps(
        {"no_adjust": sA, "with_adjust": sB,
         "saving": sA["total"] - sB["total"]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
