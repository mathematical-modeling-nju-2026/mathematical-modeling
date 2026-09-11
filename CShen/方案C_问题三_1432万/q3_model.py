"""问题3 核心模型：日前计划 + 多时点调整 + 储能按最终执行。

计费规则（题面）
  "计划购电量高于调整购电量的部分，违约电价是交易时刻电价的 50%；
   调整购电量高于计划购电量的部分，超出部分的电价是交易时刻电价的 1.5 倍。
   总的购电费用包括计划购电费用、紧急购电费用和调整购电量的相关费用。"

统一费用式（单时段 t，计划 g_p、调整 g_a、电价 p、紧急 e）
    C_t = p*min(g_p, g_a) + 0.5p*max(0, g_p - g_a) + 1.5p*max(0, g_a - g_p) + 5p*e
        = p*g_p - 0.5p*max(0, g_p - g_a) + 1.5p*max(0, g_a - g_p) + 5p*e
  引入 u = max(0, g_a - g_p)、v = max(0, g_p - g_a)，则 g_a = g_p + u - v：
    C_t = p*g_p + 1.5p*u - 0.5p*v + 5p*e

经济含义（关键）
  调减 1 kWh 计划：少付电价 p（不买了），但按 0.5p 支付违约金 → 净省 0.5p。
  所以 v 在目标里是「退款/收益」项（系数 -0.5p），这正是题目设「违约电价 50%」的用意：
  允许通过调减计划来省钱。若该电量最终仍需要，则需以 5p 紧急购电补足，
  故 LP 会权衡 0.5p 的节约与 5p·P(缺电) 的风险，不会盲目调减。
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, coo_matrix

DT = 1.0 / 6.0
T = 144
ETA = 0.90
E_MIN, E_MAX = 1200.0, 10800.0
P_MAX = 5000.0
FLOW_CAP = P_MAX * DT
EMG = 5.0
VIOL_RATIO = 0.5        # 计划高于调整：违约金为电价 50%
EXCESS_RATIO = 1.5      # 调整高于计划：超出部分为电价 1.5 倍


# ============================ 日前计划（沿用方案B）============================
def solve_plan_24h(N_plan, N_scen, w, price24, E0, E_term):
    """日前计划：H*24h 两阶段随机规划（计划净供给不等式 + 场景平衡）。

    参数
      N_plan  : (K,) 计划用的点预测净负载（kWh），K = H*144
      N_scen  : (S,TD) 场景净负载（kWh），仅约束决策日（TD=144）
      w       : (S,) 场景权重
      price24 : (144,) 单日电价，内部按 horizon 平铺
      E0/E_term: 始末电量
    返回 g_plan, c, d, E, z（长度 K）
    """
    K = N_plan.shape[0]
    H = K // T
    S, TD = N_scen.shape
    price = np.tile(np.asarray(price24, float), H)
    n = 4 * K + S * TD
    G, C, D, E = slice(0, K), slice(K, 2*K), slice(2*K, 3*K), slice(3*K, 4*K)
    EE = slice(4*K, 4*K + S*TD)

    c_obj = np.zeros(n)
    c_obj[G] = price
    px = np.asarray(price24, float)
    for s in range(S):
        c_obj[EE.start + s*TD: EE.start + (s+1)*TD] = EMG * w[s] * px[:TD]

    rows, cols, vals, b_eq = [], [], [], []
    n_eq = K + 1
    b_eq = np.zeros(n_eq)
    for k in range(K):
        pr = [(E.start + k, 1.0), (C.start + k, -ETA), (D.start + k, 1.0/ETA)]
        if k > 0:
            pr.append((E.start + k - 1, -1.0))
        else:
            b_eq[k] = E0
        for j, v in pr:
            rows.append(k); cols.append(j); vals.append(v)
    rows.append(K); cols.append(E.start + K - 1); vals.append(1.0); b_eq[K] = E_term
    A_eq = coo_matrix((vals, (rows, cols)), shape=(n_eq, n)).tocsr()

    r2, c2, v2, bl = [], [], [], []
    nr = 0
    for k in range(K):
        r2 += [nr]*3; c2 += [G.start + k, D.start + k, C.start + k]
        v2 += [-1.0, -1.0, 1.0]; bl.append(-N_plan[k]); nr += 1
    for s in range(S):
        base = EE.start + s*TD
        for t in range(TD):
            r2 += [nr]*4; c2 += [base + t, G.start + t, D.start + t, C.start + t]
            v2 += [-1.0, -1.0, -1.0, 1.0]; bl.append(-N_scen[s, t]); nr += 1
    A_ub = coo_matrix((v2, (r2, c2)), shape=(nr, n)).tocsr()
    b_ub = np.array(bl)

    lb = np.zeros(n); ub = np.full(n, np.inf)
    lb[E], ub[E] = E_MIN, E_MAX
    ub[C] = FLOW_CAP; ub[D] = FLOW_CAP
    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=list(zip(lb, ub)), method="highs")
    if res.status != 0:
        raise RuntimeError(f"计划 LP 失败: {res.message}")
    x = res.x
    g, c, d = x[G].copy(), x[C].copy(), x[D].copy()
    eff = ETA * ETA
    eps = np.minimum(c, d/eff)
    c = c - eps; d = d - eff*eps
    c[np.abs(c) < 1e-9] = 0.0; d[np.abs(d) < 1e-9] = 0.0
    return dict(g=g, c=c, d=d, E=x[E], z=g + d - c)


# ====================== 调整阶段（给定已发生的实际与预报）======================
def solve_adjust_stage(price_rem, N_scen_rem, w, E_now, g_plan_rem,
                       c_plan_rem, d_plan_rem, E_term):
    """调整阶段 LP（只覆盖剩余时段）。

    决策：调整后的购电 g_adj、储能 c/d（最终执行值）
    目标：min 计划费(已定,常数项另计) + 调增费 + 调减收益 + 紧急购电费
    约束：调整后净供给 = g_adj + d - c 需覆盖场景；储能递推；容量/功率。
    """
    K = len(price_rem)
    S, TD = N_scen_rem.shape
    T_rem = TD          # 剩余时段数（= 144 - t0）
    # 变量：g_adj(K), c(K), d(K), E(K+1 用前 K), u(K), v(K), e(S*T)
    Ng, Nc, Nd, Ne = K, K, K, K      # E 共 K 个（E_0..E_{K-1}，各时段末）
    Nu, Nv = K, K
    oG = 0
    oC = Ng
    oD = oC + Nc
    oE = oD + Nd
    oU = oE + Ne
    oV = oU + Nu
    oEe = oV + Nv
    n = oEe + S * TD

    price = np.asarray(price_rem, float)
    # 目标：1.5p*u − 0.5p*v + 5p*e（计划费 p*g_plan 为常数，不优化）
    c_obj = np.zeros(n)
    c_obj[oU:oU+K] = EXCESS_RATIO * price
    c_obj[oV:oV+K] = -VIOL_RATIO * price
    for s in range(S):
        c_obj[oEe + s*T_rem: oEe + (s+1)*T_rem] = EMG * w[s] * price[:T_rem]

    # 等式：g_adj - g_plan - u + v = 0
    rows, cols, vals, b_eq = [], [], [], []
    ne = 0
    def add_eq(r, cc_vv, b):
        nonlocal ne
        for j, v in cc_vv:
            rows.append(ne); cols.append(j); vals.append(v)
        b_eq.append(b); ne += 1
    for k in range(K):
        add_eq(ne, [(oG+k, 1.0), (oU+k, -1.0), (oV+k, 1.0)], g_plan_rem[k])
    # 储能递推: E_{k} - E_{k-1} - eta c + d/eta = 0（首段 E_0 = E_now）
    for k in range(K):
        cv = [(oE+k, 1.0), (oC+k, -ETA), (oD+k, 1.0/ETA)]
        if k > 0:
            cv.append((oE+k-1, -1.0)); b = 0.0
        else:
            b = E_now
        add_eq(ne, cv, b)
    # 终端：E_{K-1} = E_term（周期终端）
    add_eq(ne, [(oE+K-1, 1.0)], E_term)
    # 场景平衡: g_adj + d - c - e_s >= N_scen_s  →  -g-d+c+e_s <= -N_s
    A_eq = coo_matrix((vals, (rows, cols)), shape=(ne, n)).tocsr()

    r2, c2, v2, bl = [], [], [], []
    nr = 0
    for s in range(S):
        base = oEe + s * T_rem
        for t in range(T_rem):
            # 场景平衡: g + d - c + e_s >= N_s  →  -g - d + c - e_s <= -N_s
            r2 += [nr]*4; c2 += [oG+t, oD+t, oC+t, base+t]
            v2 += [-1.0, -1.0, 1.0, -1.0]; bl.append(-N_scen_rem[s, t]); nr += 1
    A_ub = coo_matrix((v2, (r2, c2)), shape=(nr, n)).tocsr()
    b_ub = np.array(bl)

    lb = np.zeros(n); ub = np.full(n, np.inf)
    lb[oE:oE+K], ub[oE:oE+K] = E_MIN, E_MAX
    ub[oC:oC+K] = FLOW_CAP
    ub[oD:oD+K] = FLOW_CAP
    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=list(zip(lb, ub)), method="highs")
    if res.status != 0:
        raise RuntimeError(f"调整 LP 失败: {res.message}")
    x = res.x
    return dict(g_adj=x[oG:oG+K], c=x[oC:oC+K], d=x[oD:oD+K], E=x[oE:oE+K+1],
                u=x[oU:oU+K], v=x[oV:oV+K], obj=float(res.fun))
