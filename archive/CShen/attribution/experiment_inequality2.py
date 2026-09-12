"""实验 v2：正确复刻 C_yang 的约束形式（无 λ、周期终端、计划下界不等式）。

关键修正：C_yang 最新版不用"终端价值 λ"，
而是 ① 计划下界 g+d-c >= N_plan（不等式） ② 周期终端（前瞻末段电量 = 前瞻起点）。

本实验对比（都用 24h 或 48h 前瞻 + 周期终端）：
  P1. 计划平衡【等式】+ 周期终端（单日）
  P2. 计划平衡【不等式】+ 周期终端（单日）      ← C_yang 思路
  P3. 不等式 + 48h 前瞻 + 周期终端              ← C_yang 主模型
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "opt_v3"))

from forecast import load_data, build_forecasts, make_scenarios, DT_HOURS, SLOTS
from optimization import PARAM, execute_day
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, diags, eye, hstack, kron

RAW = Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\raw")
data = load_data(RAW)
price = data.price
START_DAY = 31
ND = len(data.dates)


def solve_horizon(N_plan, N_scen, weights, E_init, H, ineq):
    """
    滚动前瞻随机规划。
    N_plan: (H,144) 点预测净负荷 kWh；N_scen: (S,144) 决策日场景；price: (H*144,)
    ineq=True: 计划下界 g+d-c >= N_plan（每段一个不等式）
    ineq=False: 计划净供给 = N_plan（等式，钉死在点预测）
    周期终端: 末段电量 = E_init
    """
    K = H * SLOTS
    S, T = N_scen.shape
    nvar = 4 * K + S * T
    G = slice(0, K); C = slice(K, 2*K); D = slice(2*K, 3*K); E = slice(3*K, 4*K)
    EE = slice(4*K, 4*K + S*T)

    c_obj = np.zeros(nvar)
    c_obj[G] = np.tile(price[:SLOTS], H)[:K]
    for s in range(S):
        c_obj[EE.start + s*T: EE.start + (s+1)*T] = PARAM.emergency_multiplier * weights[s] * price[:T]

    # 等式：电量递推 + 周期终端
    rows, cols, vals, b_eq = [], [], [], []
    n_eq = K + 1
    b_eq = np.zeros(n_eq)
    for k in range(K):
        pairs = [(E.start+k, 1.0), (C.start+k, -PARAM.eta_charge), (D.start+k, 1.0/PARAM.eta_discharge)]
        if k > 0:
            pairs.append((E.start+k-1, -1.0)); b_eq[k] = 0.0
        else:
            b_eq[k] = E_init
        for j, v in pairs:
            rows.append(k); cols.append(j); vals.append(v)
    # 周期终端
    rows.append(K); cols.append(E.start+K-1); vals.append(1.0); b_eq[K] = E_init
    A_eq = csr_matrix((vals, (rows, cols)), shape=(n_eq, nvar)).tocsr()

    # 不等式：场景平衡（总用）+ 计划下界（依 ineq）
    r2, c2, v2, b_list = [], [], [], []
    nrow = 0
    # 场景平衡: -g -d +c -q_s <= -N_s
    for s in range(S):
        base = EE.start + s * T
        for t in range(T):
            r2 += [nrow]*4; c2 += [base+t, G.start+t, D.start+t, C.start+t]
            v2 += [-1.0, -1.0, -1.0, 1.0]
            b_list.append(-N_scen[s, t])
            nrow += 1
    # 计划下界: -g -d +c <= -N_plan
    if ineq:
        for k in range(K):
            r2 += [nrow]*3; c2 += [G.start+k, D.start+k, C.start+k]
            v2 += [-1.0, -1.0, 1.0]
            b_list.append(-N_plan[k])
            nrow += 1
    A_ub = csr_matrix((v2, (r2, c2)), shape=(nrow, nvar)).tocsr()
    b_ub = np.array(b_list)

    limit = PARAM.power_max_kw * DT_HOURS
    bounds = [(0, None)]*K + [(0, limit)]*(2*K) + \
             [(PARAM.energy_min_kwh, PARAM.energy_max_kwh)]*K + [(0, None)]*(S*T)
    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                  method="highs",
                  options={"primal_feasibility_tolerance": 1e-8,
                           "dual_feasibility_tolerance": 1e-8})
    if not res.success:
        raise RuntimeError(res.message)
    x = res.x
    return {"grid": x[0:SLOTS], "charge": x[K:K+SLOTS], "discharge": x[2*K:2*K+SLOTS],
            "energy": x[3*K:3*K+SLOTS]}


def run(H=1, ineq=True):
    bundle = build_forecasts(data)
    e_state = PARAM.initial_energy_kwh
    tp = te = tc = 0.0
    for di in range(START_DAY, ND):
        h = min(H, ND - di)
        scen = make_scenarios(data, bundle, di, 1, PARAM.scenario_lookback)
        N_scen = (scen.load_kwh.reshape(len(scen.weights), -1) - scen.pv_kwh.reshape(len(scen.weights), -1))
        # 点预测净负荷（H 天，全用 d 之前信息）
        N_plan = np.zeros((h, SLOTS))
        for k in range(h):
            if di + k < ND:
                N_plan[k] = bundle.load_kwh[di+k, 0] - bundle.pv_kwh[di+k, 0]
            else:
                N_plan[k] = bundle.load_kwh[di, 0] - bundle.pv_kwh[di, 0]
        prices = np.tile(price, h)
        plan = solve_horizon(N_plan.reshape(-1), N_scen, scen.weights, e_state, h, ineq)
        al = data.load_kw[di] * DT_HOURS
        ap = data.pv_kw[di] * DT_HOURS
        ex = execute_day(plan, al, ap, price, e_state)
        tp += float(ex["planned_cost_yuan"].sum())
        te += float(ex["emergency_cost_yuan"].sum())
        tc += float(ex["surplus_kwh"].sum())
        e_state = float(ex["energy_end_kwh"][-1])
    return tp, te, tc


print("=" * 74)
print("约束形式对比（周期终端，无 λ）")
print("=" * 74)
if __name__ == "__main__":
    for H, ineq, desc in [(1, False, "P1 单日 · 计划等式 + 周期终端"),
                          (1, True,  "P2 单日 · 计划不等式 + 周期终端"),
                          (2, True,  "P3 48h · 计划不等式 + 周期终端"),
                          (2, False, "P4 48h · 计划等式 + 周期终端")]:
        pc, ec, cur = run(H, ineq)
        print(f"{desc}")
        print(f"   计划费={pc/1e4:>9.1f}万 紧急费={ec/1e4:>8.1f}万 总={(pc+ec)/1e4:>9.1f}万 弃电={cur/1e4:.1f}万kWh")
    print()
    print("对照: C_yang 最新版 1438.9 万；我方旧版(λ法) 1463.3 万")
