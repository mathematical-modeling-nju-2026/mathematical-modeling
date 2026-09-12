"""问题2 两阶段随机规划模型（滚动前瞻版）。

问题结构
    每天 0:00 制定当天的计划购电量 g_t 与储能充放电量 c_t/d_t。
    这些量在当天开始前就必须定下来，之后不再修改——这就是第一阶段的
    **非前瞻性**：所有场景共享同一组 (g, c, d)。
    实时偏差只有一条补救途径：紧急购电 e_t，其电价为交易时刻电价的 5 倍。

    因此场景结构是"根-叶"星形（两阶段），而不是多阶段场景树。
    多阶段分叉要到问题3（6:00/12:00/18:00 可调整）才会出现。

决策变量与"计划净供给"
    真正决定结算的是计划净供给
        z_t = g_t + d_t - c_t        （元/kWh 计费的购电量加上储能净放电）
    实际净负载 N_t 超过 z_t 的部分按 5 倍价紧急购电：
        e_t = max(0, N_t - z_t)

报童结构（本题的经济内核）
    题面："除紧急购电费用外，其他时间段的购电费用均按计划购电量计算"
    —— 计划量 g_t 无论是否用掉都要照付。于是相对于"刚好够用"：
        多计划 1 kWh：白付 p_t                        → 过量成本 c_o = p_t
        少计划 1 kWh：多付 5p_t（且原计划的 p_t 照付） → 不足成本 c_u = 4p_t
    临界分位数  F* = c_u / (c_o + c_u) = 4p / 5p = 0.80
    即：计划净供给应落在净负载条件分布的 **80% 分位**。这一点由模型自动实现，
    不需要额外约束；q2_verify 中用"无储能版本"直接验证 F* = 0.80。

    ⚠ 计划平衡必须写成不等式（而不是等式 g+d-c = N_plan）。
      等式会把 z_t 钉死在点预测上，模型就无法"多计划"；
      多计划出的电能既然用不掉，只能弃置。写成
            g_t + d_t - c_t  ≥  N_plan_t
      后，松弛量 s_t = z_t - N_plan_t 就是**超计划购电（用不掉而弃置）电量**，
      它同时吸收了光伏过剩无法消纳的部分，因此不必再单独设"弃光"变量。

储能按计划执行
    第一阶段同时给出 c_t / d_t，实时不修改。理由：单时段最大净负载缺口
    464.65 kWh 远小于储能单时段可用容量上限 833.33 kWh，实时重新调度电池
    能挽回的空间极小；而紧急购电是题面唯一明示的实时手段。这条假设把模型
    保持在两阶段，使报童结论可以被干净地检验。

滚动前瞻
    单日模型是退化的：日末储电量在本日内没有任何价值，最优解会把电池抽干到
    1200 kWh。跨日储能的真实价值只有当"明天的电价高峰"进入视野时才存在
    （本题电价曲线每日重复，深夜充电、次日早高峰放出是有利可图的）。
    故采用 H 天滚动前瞻：在 0:00 优化未来 H 天，只执行第一天，次日重优化。
    H=1 退化，H 的取值做敏感性分析。

变量布局（设 K = H×144 段，S 个场景）
    x = [ g(K) | c(K) | d(K) | E(K) | e(S×144) ]      共 4K + S·T 个

场景只加在决策日
    前瞻日不参与实际结算，其作用只是把"明天的高价时段"带进视野，从而给出
    储能的终端价值。前瞻日按点预测处理（否则要为整条前瞻链引入联合场景，
    规模爆炸且配对方式会引入人为假设）。决策日则面对完整的整日残差场景集，
    非前瞻性体现为：所有场景共享同一组 (g, c, d)。
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

DT = 1.0 / 6.0
T = 144
E_MIN, E_MAX = 1200.0, 10800.0
P_MAX = 5000.0
CAP = P_MAX * DT          # 833.33 kWh/段
ETA = 0.9
E_INIT = 6000.0
EMERGENCY_MULT = 5.0


def solve_horizon(N_plan, N_scen, weights, price,
                  E_init, E_term=None, eta=ETA, cap=CAP, E_fixed=None):
    """求解滚动前瞻的两阶段随机规划。

    参数（长度 K 为前瞻天数 × 144）
        N_plan  (K,)   计划所用的净负载点预测（kWh/段）
        N_scen  (S,T)  决策日的场景净负载（kWh/段），T=144
        weights (S,)   场景概率
        price   (K,)   电价（元/kWh），按日重复
        E_init  float  前瞻起点的储电量
        E_term  float  若给出，则强制前瞻末段储电量等于该值
                       （周期终端传 E_init，年末传 6000）
        E_fixed float  若给出，则储电量恒等于该值且充放电功率上限为 0，
                       用于构造"无储能"对照（报童临界分位数的干净检验）
    返回 dict：计划的 g/c/d/E（长度 K）、场景紧急购电 e(S,T) 与目标值。
    """
    K = N_plan.shape[0]
    S = N_scen.shape[0]
    TD = N_scen.shape[1]
    assert TD == T, f"场景只覆盖决策日，应为 {T} 段，得到 {TD}"
    n = 4 * K + S * T

    G = slice(0, K)
    C = slice(K, 2 * K)
    D = slice(2 * K, 3 * K)
    E = slice(3 * K, 4 * K)
    EE = slice(4 * K, 4 * K + S * T)

    # ---- 目标 ----
    c_obj = np.zeros(n)
    c_obj[G] = price
    px = price[:T]
    for s in range(S):
        c_obj[EE.start + s * T: EE.start + (s + 1) * T] = EMERGENCY_MULT * weights[s] * px

    # ---- 等式约束：电量递推 +（可选）终端条件 ----
    rows, cols, vals, b_eq = [], [], [], []
    n_eq = K + (1 if E_term is not None else 0)
    b_eq = np.zeros(n_eq)

    # ① 电量递推：E_k - E_{k-1} - eta*c_k + d_k/eta = 0（首段右端为 E_init）
    for k in range(K):
        pairs = [(E.start + k, 1.0), (C.start + k, -eta), (D.start + k, 1.0 / eta)]
        if k > 0:
            pairs.append((E.start + k - 1, -1.0))
            b_eq[k] = 0.0
        else:
            b_eq[k] = E_init
        for j, v in pairs:
            rows.append(k), cols.append(j), vals.append(v)
    if E_term is not None:
        rows.append(K), cols.append(E.start + K - 1), vals.append(1.0)
        b_eq[K] = E_term
    A_eq = coo_matrix((vals, (rows, cols)), shape=(n_eq, n)).tocsr()

    # ---- 不等式约束（linprog 的 A_ub 是"<="，故把 ">=" 整体取负）----
    # ② 计划净供给下界： g + d - c >= N_plan        →  -g - d + c <= -N_plan
    #    松弛量即"超计划购电（弃置）电量"，含光伏过剩无法消纳的部分
    # ③ 场景平衡： g + d - c + e_s >= N_scen_s      →  -g - d + c - e_s <= -N_scen_s
    r2, c2, v2 = [], [], []
    for k in range(K):
        r2 += [k] * 3
        c2 += [G.start + k, D.start + k, C.start + k]
        v2 += [-1.0, -1.0, 1.0]
    for s in range(S):
        base_s = EE.start + s * T
        for t in range(T):
            r = K + s * T + t
            r2 += [r] * 4
            c2 += [base_s + t, G.start + t, D.start + t, C.start + t]
            v2 += [-1.0, -1.0, -1.0, 1.0]
    A_ub = coo_matrix((v2, (r2, c2)), shape=(K + S * T, n)).tocsr()
    b_ub = -np.concatenate([N_plan, N_scen.reshape(-1)])

    # ---- 边界 ----
    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    if E_fixed is None:
        lb[E], ub[E] = E_MIN, E_MAX
        ub[C] = cap
        ub[D] = cap
    else:
        lb[E] = ub[E] = E_fixed
        lb[C] = ub[C] = 0.0
        lb[D] = ub[D] = 0.0

    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=list(zip(lb, ub)), method="highs")
    if res.status != 0:
        raise RuntimeError(f"前瞻 LP 求解失败: {res.message}")

    x = res.x
    plan = {k: x[v] for k, v in dict(g=G, c=C, d=D, E=E).items()}
    plan["z"] = plan["g"] + plan["d"] - plan["c"]      # 计划净供给
    plan["obj"] = float(res.fun)
    plan["e"] = x[EE].reshape(S, T)
    return plan


def settle_day(g, c, d, N_actual, price):
    """按题面结算单日实际费用。

    计划净供给 z_t = g_t + d_t - c_t（储能按计划执行，光伏全额优先消纳）。
    缺额 e_t = max(0, N_actual_t - z_t) 按 5 倍电价紧急购电；
    计划购电量 g_t 无论是否用掉都按 p_t 计费，用不掉的 z_t - N_t 即为
    "超计划购电（弃置）电量"。
    """
    z = g + d - c
    e = np.maximum(N_actual - z, 0.0)
    plan_cost = float(price @ g)
    emg_cost = float(EMERGENCY_MULT * (price @ e))
    return {
        "plan_cost": plan_cost,
        "emergency_cost": emg_cost,
        "total_cost": plan_cost + emg_cost,
        "emergency_kWh": float(e.sum()),
        "emergency_periods": int(np.sum(e > 1e-9)),
        "e": e,
        "z": z,
        "surplus_kWh": float(np.maximum(z - N_actual, 0.0).sum()),
    }


def verify_plan(g, c, d, E, N_plan, E_init, E_term=None, tol=1e-6):
    """逐条校验计划可行性，返回 (名称, 是否通过, 说明) 列表。"""
    z = g + d - c
    checks = []
    both = int(np.sum((c > tol) & (d > tol)))
    checks.append(("同一时段不同时充放电", both == 0, f"违反段数 = {both}"))
    checks.append(("储电量在 [1200, 10800] 内",
                   bool(E.min() >= E_MIN - 1e-3 and E.max() <= E_MAX + 1e-3),
                   f"SOC ∈ [{E.min():.2f}, {E.max():.2f}]"))
    checks.append(("起点储电量等于给定值",
                   abs(E[0] - (E_init + ETA * c[0] - d[0] / ETA)) < 1e-4,
                   f"E_init = {E_init:.2f}"))
    checks.append(("充放电功率不超限",
                   bool(c.max() <= CAP + 1e-4 and d.max() <= CAP + 1e-4),
                   f"c_max = {c.max():.2f}, d_max = {d.max():.2f} (上限 {CAP:.2f})"))
    checks.append(("计划净供给不低于点预测（等式已被松弛为不等式）",
                   bool(np.min(z - N_plan) >= -1e-6),
                   f"最小裕度 = {np.min(z - N_plan):.4f} kWh，"
                   f"超计划合计 = {np.sum(z - N_plan):,.1f} kWh"))
    E_rec = E_init + np.cumsum(ETA * c - d / ETA)
    checks.append(("电量递推自洽",
                   float(np.max(np.abs(E_rec - E))) < 1e-5,
                   f"最大偏差 = {np.max(np.abs(E_rec - E)):.2e}"))
    checks.append(("购电量非负", bool(g.min() >= -1e-7), f"g_min = {g.min():.2e}"))
    if E_term is not None:
        checks.append(("前瞻末段储电量等于终端要求",
                       abs(E[-1] - E_term) < 1e-3,
                       f"E_end = {E[-1]:.4f}, 要求 {E_term:.2f}"))
    return checks
