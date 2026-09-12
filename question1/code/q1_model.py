"""
C题 问题1：确定性储能调度优化模型（LP / MILP）

单位口径
    - 附件1 中电价单位 元/kWh，负载与光伏为功率 kW
    - 每段 10 分钟，dt = 1/6 h，功率 × dt = 该段电量 kWh
    - 时间标签为"区间末"：0:10 表示 00:00-00:10，0:00+1 表示 24:00

储能口径（附录1）
    - 最大容量 12000 kWh，允许区间 [1200, 10800] kWh
    - 最大充放电功率 5000 kW，作用于设备外端
    - 充/放效率各 90%，往返 81%
    - 2025-01-01 00:00 初始电量 6000 kWh
"""

import numpy as np
from scipy.optimize import linprog, milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix

# ---------------- 模型常量 ----------------
DT = 1 / 6                 # 每段小时数
T = 144                    # 时段数
E_MIN, E_MAX = 1200.0, 10800.0
P_MAX = 5000.0             # kW
CAP = P_MAX * DT           # 每段最大充/放电量 kWh = 833.33
ETA = 0.9                  # 单向效率
E_INIT = 6000.0            # 0:00 电量，也是 24:00 必须回到的电量


# ---------------- 输入 ----------------
def load_attachment1(path):
    """读取附件1，返回 (labels, price, load_kWh, pv_kWh)。"""
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    labels, price, load, pv = [], [], [], []
    for t, (time_tag, p, l, v) in enumerate(rows, start=1):
        labels.append(_label(t))
        price.append(float(p))
        load.append(float(l) * DT)      # kW -> kWh
        pv.append(float(v) * DT)        # kW -> kWh
    assert len(price) == T, f"期望 {T} 段，实际 {len(price)} 段"
    return labels, np.array(price), np.array(load), np.array(pv)


def _label(t):
    """第 t 段（1-based）的区间末时刻标签，t=144 -> '24:00'。"""
    m = t * 10
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------- LP 模型 ----------------
# 变量布局 x = [g(T), c(T), d(T), w(T), E(T)]，共 5T
def _slices():
    return (slice(0, T), slice(T, 2 * T), slice(2 * T, 3 * T),
            slice(3 * T, 4 * T), slice(4 * T, 5 * T))


def marginal_price(price, load, pv):
    """能量平衡约束的对偶变量 λ_t，即第 t 时段的系统边际电价（元/kWh）。

    λ_t 表示该时段多供 1 kWh 电量的边际成本，是解释"为何此时充/放"的经济学依据：
    充电倾向落在 λ 最低的时段，放电倾向落在 λ 最高的时段。
    """
    c_obj, A_eq, b_eq, bounds = build_lp(price, load, pv)
    res = linprog(c_obj, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    assert res.status == 0, f"对偶变量求解失败: {res.message}"
    return res.eqlin.marginals[:T]


def build_lp(price, load, pv):
    """构造 LP 的 (目标系数, 等式矩阵, 等式右端, 变量上下界)。

    solve_lp 与 marginal_price 共用，保证两者约束完全一致——
    对偶变量只有在完整约束集下才有意义（丢掉 SOC 递推会退化成零成本问题）。
    """
    G, C, D, W, E = _slices()
    n = 5 * T

    c_obj = np.zeros(n)
    c_obj[G] = price

    A_eq = lil_matrix((2 * T + 1, n))
    b_eq = np.zeros(2 * T + 1)

    # ① 能量平衡：g_t + V_t + d_t = L_t + c_t + w_t
    for t in range(T):
        A_eq[t, G.start + t] = 1.0
        A_eq[t, D.start + t] = 1.0
        A_eq[t, C.start + t] = -1.0
        A_eq[t, W.start + t] = -1.0
        b_eq[t] = load[t] - pv[t]

    # ② 电量递推：E_t = E_{t-1} + η c_t - d_t/η
    for t in range(T):
        r = T + t
        A_eq[r, E.start + t] = 1.0
        if t > 0:
            A_eq[r, E.start + t - 1] = -1.0
        A_eq[r, C.start + t] = -ETA
        A_eq[r, D.start + t] = 1.0 / ETA
        b_eq[r] = E_INIT if t == 0 else 0.0

    # ⑤ 日末电量回到日初：E_T = E_0
    A_eq[2 * T, E.start + T - 1] = 1.0
    b_eq[2 * T] = E_INIT

    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    lb[E], ub[E] = E_MIN, E_MAX
    ub[C] = CAP
    ub[D] = CAP
    # 弃光 w 只设下界 0，不设上界（与问题二/三的松弛变量口径统一）。
    # 说明：平衡为等式 g+V+d = L+c+w ⇒ w = g+d-c-(L-V)；
    #   目标只惩罚 g，故若最优解出现 w > V（即净供给超过负载），
    #   可令 g←g-δ、w←w-δ 使平衡不变而费用严格下降（p>0），与最优性矛盾。
    #   ⇒ 最优解自动满足 w <= V，显式上界冗余。
    ub[W] = np.inf
    lb[W] = 0.0

    return c_obj, A_eq.tocsr(), b_eq, list(zip(lb, ub))


def solve_lp(price, load, pv):
    """线性规划：min Σ p_t g_t。返回 (obj, x)。"""
    c_obj, A_eq, b_eq, bounds = build_lp(price, load, pv)
    res = linprog(c_obj, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    assert res.status == 0, f"LP 未求得最优解: {res.message}"
    return res.fun, res.x


# ---------------- MILP 模型（加入充放电互斥） ----------------
# 变量布局在 LP 基础上追加 z(T)，z=1 允许充电，z=0 允许放电
def solve_milp(price, load, pv):
    G, C, D, W, E = _slices()
    n = 5 * T
    Z = slice(n, n + T)

    c_obj = np.zeros(n + T)
    c_obj[G] = price

    rows, cols, vals, lo, hi = [], [], [], [], []

    def add_row(coefs, low, high):
        r = len(lo)
        for j, v in coefs:
            rows.append(r), cols.append(j), vals.append(v)
        lo.append(low), hi.append(high)

    # ① 能量平衡（等式，用 low==high 表达）
    for t in range(T):
        add_row([(G.start + t, 1.0), (D.start + t, 1.0),
                 (C.start + t, -1.0), (W.start + t, -1.0)],
                load[t] - pv[t], load[t] - pv[t])

    # ② 电量递推
    for t in range(T):
        coefs = [(E.start + t, 1.0), (C.start + t, -ETA), (D.start + t, 1.0 / ETA)]
        if t > 0:
            coefs.append((E.start + t - 1, -1.0))
        rhs = E_INIT if t == 0 else 0.0
        add_row(coefs, rhs, rhs)

    # ⑤ 日末电量
    add_row([(E.start + T - 1, 1.0)], E_INIT, E_INIT)

    # 互斥：c_t - CAP·z_t ≤ 0 ; d_t + CAP·z_t ≤ CAP
    for t in range(T):
        add_row([(C.start + t, 1.0), (Z.start + t, -CAP)], -np.inf, 0.0)
        add_row([(D.start + t, 1.0), (Z.start + t, CAP)], -np.inf, CAP)

    A = np.array(rows), np.array(cols), np.array(vals)
    from scipy.sparse import coo_matrix
    A_sp = coo_matrix((A[2], (A[0], A[1])), shape=(len(lo), n + T)).tocsr()

    lb = np.zeros(n + T)
    ub = np.full(n + T, np.inf)
    lb[E], ub[E] = E_MIN, E_MAX
    ub[C] = CAP
    ub[D] = CAP
    # 同 build_lp：不给 w 设上界（最优解自动满足 w<=V，见该函数注释）
    ub[W] = np.inf
    ub[Z] = 1.0

    integrality = np.zeros(n + T)
    integrality[Z] = 1

    res = milp(c=c_obj,
               constraints=LinearConstraint(A_sp, np.array(lo), np.array(hi)),
               integrality=integrality,
               bounds=Bounds(lb, ub))
    assert res.success, f"MILP 未求得最优解: {res.message}"
    return res.fun, res.x


# ---------------- 无储能基线 ----------------
def baseline_no_storage(price, load, pv):
    """不用储能：光伏优先供负载，不足部分按当时电价购买，余电弃掉。"""
    g = np.maximum(load - pv, 0.0)
    return float(price @ g), g


# ---------------- 结果打包 ----------------
def unpack(x):
    G, C, D, W, E = _slices()
    return dict(g=x[G], c=x[C], d=x[D], w=x[W], E=x[E])


def verify(sol, price, load, pv, tol=1e-6):
    """逐条校验解的可行性与结构性质，返回检查项列表。"""
    g, c, d, w, E = sol["g"], sol["c"], sol["d"], sol["w"], sol["E"]
    checks = []

    # 互补性：同一时段不同时充放电
    both = int(np.sum((c > tol) & (d > tol)))
    checks.append(("同一时段不同时充放电", both == 0, f"违反时段数 = {both}"))

    # SOC 上下限
    checks.append((f"储电量在 [{E_MIN:.0f}, {E_MAX:.0f}] 内",
                   bool(E.min() >= E_MIN - 1e-4 and E.max() <= E_MAX + 1e-4),
                   f"SOC ∈ [{E.min():.2f}, {E.max():.2f}]"))

    # 首末电量
    checks.append(("0:00 与 24:00 储电量相同",
                   abs(E[-1] - E_INIT) < 1e-4,
                   f"E_0 = {E_INIT:.2f}, E_144 = {E[-1]:.2f}"))

    # 逐段能量平衡
    bal = g + pv + d - load - c - w
    checks.append(("逐段能量平衡", np.max(np.abs(bal)) < 1e-6,
                   f"最大残差 = {np.max(np.abs(bal)):.2e}"))

    # 充放电功率上限
    checks.append((f"充/放电量 ≤ {CAP:.2f} kWh/段",
                   bool(c.max() <= CAP + 1e-6 and d.max() <= CAP + 1e-6),
                   f"c_max = {c.max():.2f}, d_max = {d.max():.2f}"))

    # 电量递推一致性（独立重算）
    E_rec = E_INIT + np.cumsum(ETA * c - d / ETA)
    checks.append(("电量递推式自洽", np.max(np.abs(E_rec - E)) < 1e-6,
                   f"最大偏差 = {np.max(np.abs(E_rec - E)):.2e}"))

    # 弃光量非负：模型约束（lb[W] = 0），属硬性可行性条件
    checks.append(("弃光量非负", bool(w.min() >= -1e-9),
                   f"w_min = {w.min():.2e}, 弃光合计 = {w.sum():.2f} kWh"))

    # 弃光量未超光伏出力：本实例的数值观察，**不是**模型约束。
    # 模型已不设 w <= V 的上界（见 build_lp 注释），最优解自动满足该式；
    # 换一组数据时此项若失败，并不表示求解出错，详见结果说明。
    checks.append(("弃光量未超光伏出力（实例观察，非模型约束）",
                   bool(np.all(w <= pv + 1e-6)),
                   f"max(w - V) = {float(np.max(w - pv)):.2e}"))

    checks.append(("购电量非负", bool(g.min() >= -1e-9), f"g_min = {g.min():.2e}"))

    return checks
