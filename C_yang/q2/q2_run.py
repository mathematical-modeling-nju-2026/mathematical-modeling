"""问题2 全年滚动仿真驱动。

三种规划模式共用同一套模型与前瞻机制，只改变"计划依据什么"：
    perfect       完美预见：计划直接看到当天实际净负载（理论下界，紧急购电恒为 0）
    deterministic 确定性规划：计划只用净负载点预测，忽略不确定性
    stochastic    随机规划：计划面对整日残差场景集（主模型）

结算统一按题面：计划购电量按 p_t 计费，缺额按 5p_t 紧急购电。

时间口径
    全年 365 天滚动，1 月作为预测器与滚动机制的预热期；
    结果按附件5 要求从 2025.2.1 报到 12.31（334 天）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from q2_data import DT, T, load_attachment1, load_attachment2, net_load
from q2_forecast import best_forecaster
from q2_model import (CAP, E_INIT, E_MAX, E_MIN, solve_horizon, settle_day)
from q2_scenarios import build_scenarios

YEAR_DAYS = 365
REPORT_FROM = 31          # 2025.2.1（0-based）
E_YEAR_END = E_INIT       # 年末储能回到 6000 kWh，保证与基线可比


@dataclass
class SimConfig:
    mode: str = "stochastic"      # perfect | deterministic | stochastic
    horizon: int = 2              # 前瞻天数 H
    n_scen: int = None            # 场景削减后的场景数 S；None=用整个窗口（默认）
    window: int = 56              # 场景窗口天数
    terminal: str = "cyclic"      # cyclic: 前瞻末端回到前瞻起点电量（默认）
                                  # none  : 无终端条件（会前甩储能，仅作对照）
    no_storage: bool = False      # 关闭储能（用于验证报童临界分位数 F*=0.80）
    seed: int = 20250911
    report_from: int = REPORT_FROM
    n_days: int = YEAR_DAYS       # 仿真天数（调试时可缩短）
    verbose: bool = True


@dataclass
class SimResult:
    mode: str
    horizon: int
    n_scen: int
    g: np.ndarray = None          # (365, T) 计划购电量 kWh
    c: np.ndarray = None
    d: np.ndarray = None
    z: np.ndarray = None          # (365, T) 计划净供给 g+d-c，kWh
    E_traj: np.ndarray = None     # (365, T) 当日各时段末储电量 kWh（逐段轨迹）
    E_end: np.ndarray = None      # (365,) 每日 24:00 储电量
    E_start: np.ndarray = None    # (365,) 每日 0:00 储电量
    e: np.ndarray = None          # (365, T) 紧急购电量 kWh
    plan_cost: np.ndarray = None  # (365,)
    emg_cost: np.ndarray = None
    fc: np.ndarray = None         # (365, T) 当日净负载点预测 kWh
    N: np.ndarray = None          # (365, T) 实际净负载 kW（用于弃置量等事后统计）
    elapsed: float = 0.0
    extra: dict = field(default_factory=dict)

    def slice_report(self, i0):
        return slice(i0, YEAR_DAYS)


def simulate(L, V, price, cfg: SimConfig):
    """全年滚动仿真，返回 SimResult。"""
    ND = cfg.n_days
    N = net_load(L, V)
    fc_model = best_forecaster()
    R = fc_model.residual(L, V)                       # 历史整日残差（因果）
    FC = fc_model.matrix(L, V, 0)                     # 每日点预测（因果）

    out = SimResult(mode=cfg.mode, horizon=cfg.horizon, n_scen=cfg.n_scen)
    for nm, shp in [("g", (ND, T)), ("c", (ND, T)),
                    ("d", (ND, T)), ("z", (ND, T)),
                    ("e", (ND, T)), ("E_traj", (ND, T))]:
        setattr(out, nm, np.zeros(shp))
    for nm in ("E_end", "E_start", "plan_cost", "emg_cost"):
        setattr(out, nm, np.zeros(ND))
    out.fc = FC * DT
    out.N = N

    E_now = E_INIT
    E_fixed = E_INIT if cfg.no_storage else None
    t0 = time.time()
    for d in range(ND):
        H = min(cfg.horizon, ND - d)
        days = list(range(d, d + H))
        K = H * T

        if cfg.mode == "perfect":
            # 完美预见：场景退化为"当天实际净负载"这一个点，紧急购电恒为 0
            N_plan = np.concatenate([N[j] * DT for j in days])
            N_scen = (N[d] * DT)[None, :].copy()
            wts = np.array([1.0])
        else:
            # 前瞻矩阵必须按"截止到第 d-1 天"的信息算：第 d 天 0:00 时
            # 第 d 天的实际值还没发生，前瞻日不能偷看它（见 horizon_matrix）
            N_plan = fc_model.horizon_matrix(L, V, d, H).reshape(-1) * DT
            if cfg.mode == "deterministic":
                N_scen = (FC[d] * DT)[None, :].copy()
                wts = np.array([1.0])
            else:
                # 场景只覆盖决策日；前瞻日按点预测处理
                sc, wts = build_scenarios(R, d, FC[d], S=cfg.n_scen,
                                          window=cfg.window)
                N_scen = sc * DT

        # 终端条件：年末强制回到初始电量；其余日用"周期终端"消除自由终端的甩负荷偏置
        if cfg.no_storage:
            E_term = E_INIT                    # 储电量恒定，终端条件自动满足
        elif days[-1] == ND - 1:
            E_term = E_YEAR_END
        elif cfg.terminal == "cyclic":
            E_term = E_now
        else:
            E_term = None
        plan = solve_horizon(N_plan, N_scen, wts,
                             np.tile(price, H), E_now, E_term=E_term,
                             E_fixed=E_fixed)

        g0, c0, d0 = plan["g"][:T], plan["c"][:T], plan["d"][:T]
        out.g[d], out.c[d], out.d[d] = g0, c0, d0
        out.z[d] = g0 + d0 - c0
        out.E_start[d] = E_now
        out.E_traj[d] = plan["E"][:T]
        E_now = E_INIT if cfg.no_storage else float(plan["E"][T - 1])
        out.E_end[d] = E_now

        st = settle_day(g0, c0, d0, N[d] * DT, price)
        out.e[d] = st["e"]
        out.plan_cost[d] = st["plan_cost"]
        out.emg_cost[d] = st["emergency_cost"]

        if cfg.verbose and (d % 30 == 0 or d == ND - 1):
            print(f"    [{cfg.mode} H={cfg.horizon} S={cfg.n_scen}] "
                  f"第 {d + 1:3d}/{ND} 天  累计 {time.time() - t0:6.1f}s  "
                  f"E={E_now:8.1f}")

    out.elapsed = time.time() - t0
    return out


def summarize(res: SimResult, i0=REPORT_FROM):
    sl = slice(i0, len(res.g))
    tot = res.plan_cost[sl].sum() + res.emg_cost[sl].sum()
    return {
        "mode": res.mode,
        "horizon": res.horizon,
        "n_scen": res.n_scen,
        "days": len(res.g) - i0,
        "total_cost": float(tot),
        "plan_cost": float(res.plan_cost[sl].sum()),
        "emg_cost": float(res.emg_cost[sl].sum()),
        "emg_kWh": float(res.e[sl].sum()),
        "emg_periods": int(np.sum(res.e[sl] > 1e-9)),
        "emg_days": int(np.sum(res.e[sl].sum(axis=1) > 1e-9)),
        "g_kWh": float(res.g[sl].sum()),
        "charge_kWh": float(res.c[sl].sum()),
        "discharge_kWh": float(res.d[sl].sum()),
        # 计划裕度：计划净供给超出点预测的部分（报童"过量"一侧）
        "margin_kWh": float(np.maximum(res.z[sl] - res.fc[sl], 0.0).sum()),
        # 弃置电量：计划净供给超出**实际**净负载、用不掉只能弃掉的部分
        "dump_kWh": float(np.maximum(res.z[sl] - res.N[sl] * DT, 0.0).sum()),
        "E_end_final": float(res.E_end[len(res.g) - 1]),
        "elapsed": res.elapsed,
    }


def baseline_no_storage(L, V, price, mode="perfect", FC=None):
    """无储能基线：B0 完美预见（直接买实际净负载）/ B1 按预测计划（含紧急购电）。"""
    ND = L.shape[0]
    N = net_load(L, V) * DT
    P = np.tile(price, ND).reshape(ND, T)
    if mode == "perfect":
        g = np.maximum(N, 0.0)
        return dict(plan_cost=float((P * g).sum()),
                    emg_cost=0.0, emg_kWh=0.0,
                    total_cost=float((P * g).sum()))
    g = np.maximum(FC * DT, 0.0)
    e = np.maximum(N - g, 0.0)
    return dict(plan_cost=float((P * g).sum()),
                emg_cost=float(5.0 * (P * e).sum()),
                emg_kWh=float(e.sum()),
                total_cost=float((P * g).sum() + 5.0 * (P * e).sum()))


if __name__ == "__main__":
    dates, L, V = load_attachment2()
    _, price, _, _ = load_attachment1()
    cfg = SimConfig(mode="stochastic", horizon=2, n_scen=20, n_days=40, verbose=True)
    res = simulate(L, V, price, cfg)
    print(summarize(res, 31))
