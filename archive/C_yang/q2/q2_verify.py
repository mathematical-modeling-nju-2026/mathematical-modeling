"""问题2 对照基准与结果校验。

对照基准（逐层剥开，量化每一层的经济价值）
    B0  无储能 · 完美预见     直接买实际净负载，紧急购电恒为 0
    B1  无储能 · 按预测计划   计划 = 点预测的正部，缺额按 5 倍价紧急购电
    B2  有储能 · 确定性规划   计划只用点预测，忽略不确定性
    B3  有储能 · 随机规划     主模型：计划面对整日残差场景集
    B4  有储能 · 完美预见     理论下界，紧急购电恒为 0
    B2' 有储能 · 每日回充     等价于 H=1 + 日末回到日初（问题1 的口径），
                             用来量化"允许储能跨日"的价值

校验项
    ① 非前瞻性：决策日的计划不得使用决策日的实际值
    ② 报童临界分位数：计划覆盖应落在净负载条件分布的 80% 分位附近
    ③ 逐段能量平衡、SOC 边界与递推、充放电功率上限
    ④ 紧急购电与实际缺口一致，且计划购电量恒非负
"""

from __future__ import annotations

import numpy as np

from q2_data import DT, T, load_attachment1, load_attachment2, net_load
from q2_forecast import best_forecaster
from q2_model import (CAP, E_INIT, E_MAX, E_MIN, ETA, EMERGENCY_MULT,
                      solve_horizon)
from q2_scenarios import build_scenarios


# ---------------- 非前瞻性检验 ----------------

def check_causality(L, V, price, days=(31, 60, 150, 240, 330), delta=3000.0):
    """把决策日的实际净负载改写成一个荒谬值，重算计划；计划应完全不变。

    整个决策链——点预测 FC、历史残差 R、场景集——在构造上只依赖决策日
    **之前**的数据，因此这一扰动不应对 (g, c, d) 产生任何影响。
    为让检验真正有杀伤力，扰动后点预测、残差、场景集全部重算（而不是沿用
    旧值），任何一处泄漏了决策日实际值都会被这张网捞出来。
    """
    fc = best_forecaster()
    R, FC = fc.residual(L, V), fc.matrix(L, V, 0)
    rows = []
    for d in days:
        j = min(d + 1, L.shape[0] - 1)
        N_plan = fc.horizon_matrix(L, V, d, 2).reshape(-1) * DT
        sc, w = build_scenarios(R, d, FC[d])
        base = solve_horizon(N_plan, sc * DT, w,
                             np.tile(price, 2), E_INIT, E_term=E_INIT)

        L2 = L.copy()
        L2[d] = L2[d] + delta                      # 篡改决策日的实际负载
        R2, FC2 = fc.residual(L2, V), fc.matrix(L2, V, 0)
        N_plan2 = fc.horizon_matrix(L2, V, d, 2).reshape(-1) * DT
        sc2, w2 = build_scenarios(R2, d, FC2[d])
        pert = solve_horizon(N_plan2, sc2 * DT, w2,
                             np.tile(price, 2), E_INIT, E_term=E_INIT)

        dev = max(float(np.max(np.abs(base[k] - pert[k])))
                  for k in ("g", "c", "d", "E"))
        rows.append((d, dev))
    return rows


def check_scenario_independence(L, V, days=(60, 150, 240, 330)):
    """场景集必须只由决策日之前的历史残差构成：把未来某天的负载改掉，场景集不变。"""
    fc = best_forecaster()
    R = fc.residual(L, V)
    FC = fc.matrix(L, V, 0)
    rows = []
    for d in days:
        sc, w = build_scenarios(R, d, FC[d])
        L2 = L.copy()
        L2[min(d + 30, 364)] += 5000.0
        R2 = fc.residual(L2, V)
        sc2, w2 = build_scenarios(R2, d, FC[d])
        rows.append((d, float(np.max(np.abs(sc - sc2)))))
    return rows


# ---------------- 报童临界分位数检验 ----------------

def coverage_rate(res, R, FC, days_slice, tol=1e-9):
    """计划净供给 z_t = g_t + d_t - c_t 在决策日场景分布中的覆盖分位数。

    报童结论：多计划 1 kWh 白付 p，少计划 1 kWh 多付 4p，
    临界分位数 F* = 4p/(p+4p) = 0.80。故 z_t 的"场景覆盖率"应聚集在 0.80；
    偏离说明该时段被储能功率 / SOC 边界卡住（例如峰段放电放满、谷段充满）。

    ⚠ 单位：res.* 全部是 kWh，build_scenarios 返回的是 kW，必须乘 DT 才能比。
    """
    covs = []
    for i in days_slice:
        sc, w = build_scenarios(R, i, FC[i])
        z = res.z[i]
        below = (sc * DT <= z[None, :] + tol).astype(float)
        covs.append((w[:, None] * below).sum(axis=0))
    return np.array(covs)


# ---------------- 结构校验 ----------------

def structural_checks(res, L, V, i0, i1, price):
    N = net_load(L, V) * DT
    checks = []

    # ① 计划净供给不低于点预测（不等式松弛量 = 超计划购电/弃置电量）
    marg = res.z[i0:i1] - res.fc[i0:i1]
    checks.append(("计划净供给 ≥ 净负载点预测",
                   bool(marg.min() >= -1e-6),
                   f"最小裕度 = {marg.min():.2e} kWh，超计划合计 = "
                   f"{np.maximum(res.z[i0:i1] - N[i0:i1], 0).sum():,.1f} kWh"))

    # ② 实际缺口与紧急购电一致
    e_exp = np.maximum(N[i0:i1] - res.z[i0:i1], 0.0)
    dev = float(np.max(np.abs(e_exp - res.e[i0:i1])))
    checks.append(("紧急购电 = max(0, 实际净负载 - 计划净供给)",
                   dev < 1e-6, f"最大偏差 = {dev:.2e} kWh"))

    # ②' 计划净供给自洽：z = g + d - c
    dev_z = float(np.max(np.abs(res.z[i0:i1] - (res.g[i0:i1] + res.d[i0:i1]
                                                - res.c[i0:i1]))))
    checks.append(("计划净供给定义自洽 z = g + d - c",
                   dev_z < 1e-6, f"最大偏差 = {dev_z:.2e} kWh"))

    # ③ SOC 边界
    allE = np.concatenate([res.E_start[i0:i1], res.E_end[i0:i1]])
    checks.append(("储电量在 [1200, 10800] 内",
                   bool(allE.min() >= E_MIN - 1e-3 and allE.max() <= E_MAX + 1e-3),
                   f"SOC ∈ [{allE.min():.2f}, {allE.max():.2f}]"))

    # ④ 充放电功率上限与互斥
    c, d = res.c[i0:i1], res.d[i0:i1]
    checks.append(("充放电功率不超限",
                   bool(c.max() <= CAP + 1e-4 and d.max() <= CAP + 1e-4),
                   f"c_max = {c.max():.2f}, d_max = {d.max():.2f} (上限 {CAP:.2f})"))
    both = int(np.sum((c > 1e-6) & (d > 1e-6)))
    checks.append(("同一时段不同时充放电", both == 0, f"违反段数 = {both}"))

    # ⑤ 计划购电量非负
    checks.append(("计划购电量非负",
                   bool(res.g[i0:i1].min() >= -1e-7),
                   f"g_min = {res.g[i0:i1].min():.2e}"))

    # ⑥ SOC 跨日衔接：当日 24:00 = 次日 0:00
    dev2 = float(np.max(np.abs(res.E_end[i0:i1 - 1] - res.E_start[i0 + 1:i1])))
    checks.append(("跨日储电量连续（当日 24:00 = 次日 0:00）",
                   dev2 < 1e-6, f"最大偏差 = {dev2:.2e} kWh"))

    # ⑦ 年末储电量
    checks.append(("年末（12.31 24:00）储电量 = 6000",
                   abs(res.E_end[i1 - 1] - E_INIT) < 1e-3,
                   f"E = {res.E_end[i1 - 1]:.4f}"))

    # ⑧ 全年往返损失非负
    loss = float(res.c[i0:i1].sum() - res.d[i0:i1].sum()
                 - (res.E_end[i1 - 1] - res.E_start[i0]))
    checks.append(("储能往返损失 ≥ 0",
                   loss >= -1e-6, f"往返损失 = {loss:,.1f} kWh"))
    return checks


def fractile_report(res, R, FC, i0, i1):
    """覆盖率统计：均值、中位数、落在 [0.7,0.9] 的比例、按时段均值。"""
    cov = coverage_rate(res, R, FC, range(i0, i1))
    return {
        "mean": float(cov.mean()),
        "median": float(np.median(cov)),
        "in_band": float(np.mean((cov >= 0.70) & (cov <= 0.90))),
        "realized_shortfall_rate": float(np.mean(res.e[i0:i1] > 1e-6)),
        # 逐小时平均覆盖率（144 段 = 24 小时 × 6 段），看储能把覆盖率推高/压低在哪
        "by_hour": cov.reshape(-1, 24, 6).mean(axis=(0, 2)).tolist(),
    }


def fractile_no_storage(L, V, price, i0, i1, horizon=2):
    """关闭储能后的随机规划：报童临界分位数的干净检验。

    没有储能，各时段解耦，最优计划净供给应严格落在净负载条件分布的
    80% 分位。实测覆盖率越接近 0.80，说明"多计划白付 p、少计划多付 4p"
    这一经济结构被模型正确捕捉。
    """
    import numpy as _np
    from q2_run import SimConfig, simulate
    cfg = SimConfig(mode="stochastic", horizon=horizon, n_scen=None,
                    no_storage=True, verbose=False)
    res = simulate(L, V, price, cfg)
    fc = best_forecaster()
    R, FC = fc.residual(L, V), fc.matrix(L, V, 0)
    cov = coverage_rate(res, R, FC, range(i0, i1))
    return {
        "mean": float(cov.mean()),
        "median": float(np.median(cov)),
        "in_band": float(np.mean((cov >= 0.75) & (cov <= 0.85))),
        "cost": float(res.plan_cost[i0:i1].sum() + res.emg_cost[i0:i1].sum()),
        "emg_kWh": float(res.e[i0:i1].sum()),
        "g_kWh": float(res.g[i0:i1].sum()),
        "days": int(i1 - i0),
    }
