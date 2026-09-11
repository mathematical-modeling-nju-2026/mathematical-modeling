"""问题2 主流程：跑全部规划模式与对照基准 -> 校验 -> 导出结果。

用法
    python3 q2_main.py            # 默认配置（见 HORIZON）
    python3 q2_main.py --sweep    # 只跑前瞻长度/场景数敏感性
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from q2_data import DT, T, load_attachment1, load_attachment2, net_load
from q2_export import export_daily_summary, export_detail, export_result2
from q2_forecast import BEST_SPEC, best_forecaster
from q2_model import CAP, E_INIT, EMERGENCY_MULT
from q2_run import (E_YEAR_END, REPORT_FROM, SimConfig, baseline_no_storage,
                    simulate, summarize)
from q2_scenarios import build_scenarios
from q2_verify import (check_causality, check_scenario_independence,
                       fractile_no_storage, fractile_report, structural_checks)

HERE = Path(__file__).parent
OUT = HERE
HORIZON = 2                    # 主模型前瞻天数（由敏感性分析确定，见 --sweep）


def run_all(L, V, price, horizon=HORIZON, verbose=True):
    res = {}
    for mode in ("stochastic", "deterministic", "perfect"):
        cfg = SimConfig(mode=mode, horizon=horizon, n_scen=None, verbose=verbose)
        t = time.time()
        res[mode] = simulate(L, V, price, cfg)
        if verbose:
            print(f"  {mode:<14} 完成，用时 {time.time() - t:5.1f}s")
    return res


def report(results, L, V, price, i0=REPORT_FROM):
    fc = best_forecaster()
    FC = fc.matrix(L, V, 0)
    R = fc.residual(L, V)
    i1 = L.shape[0]

    lines = []
    add = lines.append

    add("=" * 84)
    add("问题2  结果汇总（结算区间 2025.2.1 - 12.31，共 %d 天）" % (i1 - i0))
    add("=" * 84)

    # ---- 对照基准 ----
    P = np.tile(price, i1).reshape(i1, T)
    N = net_load(L, V) * DT
    base0 = float((P[i0:i1] * np.maximum(N[i0:i1], 0)).sum())
    g1 = np.maximum(FC[i0:i1] * DT, 0.0)
    e1 = np.maximum(N[i0:i1] - g1, 0.0)
    base1 = float((P[i0:i1] * g1).sum() + EMERGENCY_MULT * (P[i0:i1] * e1).sum())
    base1_emg = float(e1.sum())

    s = {k: summarize(v, i0) for k, v in results.items()}
    # B1'：关掉储能跑同一个随机规划，用来干净地检验报童临界分位数 F*=0.80
    ns = fractile_no_storage(L, V, price, i0, i1)
    b4 = s["perfect"]["total_cost"]
    b3 = s["stochastic"]["total_cost"]
    b2 = s["deterministic"]["total_cost"]

    add("")
    add(f"  {'方案':<34}{'总购电费(元)':>16}{'紧急购电量(kWh)':>18}{'较 B0 节省':>16}")
    add("  " + "-" * 82)
    rows = [
        ("B0 无储能 · 完美预见", base0, 0.0),
        ("B1 无储能 · 按预测计划（含紧急购电）", base1, base1_emg),
        ("B1' 无储能 · 随机规划（报童 80% 分位）", ns["cost"], ns["emg_kWh"]),
        ("B2 有储能 · 确定性规划", b2, s["deterministic"]["emg_kWh"]),
        ("B3 有储能 · 随机规划（主模型）", b3, s["stochastic"]["emg_kWh"]),
        ("B4 有储能 · 完美预见（理论下界）", b4, s["perfect"]["emg_kWh"]),
    ]
    for name, cost, e in rows:
        add(f"  {name:<34}{cost:>16,.2f}{e:>18,.1f}"
            f"{(base0 - cost) / base0 * 100:>15.2f}%")

    add("")
    add("  分层价值分解：")
    add(f"    储能在完美预见下的价值 (B0-B4)        : {base0 - b4:>14,.2f} 元"
        f"  ({(base0 - b4) / base0 * 100:5.2f}%)")
    add(f"    预测不确定性造成的损失 (B4-B3)        : {b4 - b3:>14,.2f} 元"
        f"  ({(b4 - b3) / base0 * 100:5.2f}%)")
    add(f"    随机建模相对确定性规划的价值 (B2-B3)  : {b2 - b3:>14,.2f} 元"
        f"  ({(b2 - b3) / base0 * 100:5.2f}%)")
    add(f"    主模型总节省 (B0-B3)                  : {base0 - b3:>14,.2f} 元"
        f"  ({(base0 - b3) / base0 * 100:5.2f}%)")

    # ---- 主模型明细 ----
    add("")
    add("-" * 84)
    add("主模型（B3 随机规划）明细")
    add("-" * 84)
    add(f"  全天购电量合计        : {s['stochastic']['g_kWh']:>14,.1f} kWh")
    add(f"  其中计划购电费        : {s['stochastic']['plan_cost']:>14,.2f} 元")
    add(f"  紧急购电量            : {s['stochastic']['emg_kWh']:>14,.1f} kWh")
    add(f"  紧急购电费            : {s['stochastic']['emg_cost']:>14,.2f} 元")
    add(f"  紧急购电时段数        : {s['stochastic']['emg_periods']:>14,} 段"
        f"  （占 {s['stochastic']['emg_periods'] / ((i1 - i0) * T) * 100:.1f}%）")
    add(f"  发生紧急购电的天数    : {s['stochastic']['emg_days']:>14,} 天"
        f"  （占 {s['stochastic']['emg_days'] / (i1 - i0) * 100:.1f}%）")
    add(f"  日均紧急购电量        : {s['stochastic']['emg_kWh'] / (i1 - i0):>14,.1f} kWh")
    add(f"  储能充电量            : {s['stochastic']['charge_kWh']:>14,.1f} kWh")
    add(f"  储能放电量            : {s['stochastic']['discharge_kWh']:>14,.1f} kWh")
    add(f"  弃置电量(计划用不掉)  : {s['stochastic']['dump_kWh']:>14,.1f} kWh"
        f"  （占计划净供给 {s['stochastic']['dump_kWh'] / s['stochastic']['g_kWh'] * 100:.2f}%）")
    add(f"  年末储电量            : {s['stochastic']['E_end_final']:>14,.1f} kWh")

    # ---- 校验 ----
    add("")
    add("-" * 84)
    add("结构校验")
    add("-" * 84)
    checks = structural_checks(results["stochastic"], L, V, i0, i1, price)
    for name, ok, detail in checks:
        add(f"  [{'✓' if ok else '✗'}] {name:<44} {detail}")

    add("")
    add("非前瞻性校验（篡改决策日的实际负载，计划必须完全不变）")
    for d, dev in check_causality(L, V, price):
        add(f"  [{'✓' if dev < 1e-9 else '✗'}] 第 {d + 1:3d} 天  扰动后计划最大变化 = {dev:.2e}")
    add("场景集因果性校验（篡改决策日之后 30 天的负载，场景集必须不变）")
    for d, dev in check_scenario_independence(L, V):
        add(f"  [{'✓' if dev < 1e-9 else '✗'}] 第 {d + 1:3d} 天  扰动后场景最大变化 = {dev:.2e}")

    # ---- 报童分位数 ----
    add("")
    add("-" * 84)
    add("报童临界分位数校验（紧急电价为 5 倍 -> 最优覆盖 F* = 1 - 1/5 = 0.80）")
    add("-" * 84)
    for mode in ("stochastic", "deterministic"):
        fr = fractile_report(results[mode], R, FC, i0, i1)
        add(f"  {mode:<14} 计划覆盖率 均值 {fr['mean']:.3f}  中位数 {fr['median']:.3f}"
            f"   落在 [0.70,0.90] 的时段占比 {fr['in_band'] * 100:5.1f}%"
            f"   实际缺口频率 {fr['realized_shortfall_rate'] * 100:5.1f}%")

    return lines, dict(base0=base0, base1=base1, b1ns=ns["cost"],
                       b2=b2, b3=b3, b4=b4)


def _sweep_row(tag, cfg, L, V, price):
    t = time.time()
    res = simulate(L, V, price, cfg)
    s = summarize(res, REPORT_FROM)
    E = res.E_end[REPORT_FROM:]
    print(f"  {tag:<30}{s['total_cost']:>15,.0f}{s['emg_kWh']:>15,.0f}"
          f"{E.mean():>10.0f}{s['g_kWh']:>14,.0f}{time.time() - t:>9.1f}")
    return s, float(E.mean())


def sweep(L, V, price):
    """敏感性分析：前瞻长度 H、终端条件、场景窗口/场景数。"""
    print("=" * 96)
    print("问题2  敏感性分析")
    print("=" * 96)
    hdr = (f"  {'配置':<30}{'总成本(元)':>15}{'紧急电量(kWh)':>15}"
           f"{'SOC均值':>10}{'购电量(kWh)':>14}{'耗时(s)':>9}")

    print()
    print("A. 前瞻长度 H（周期终端，56 天窗口，全窗口不削减）")
    print(hdr)
    print("  " + "-" * 94)
    for H in (1, 2, 3, 4, 7):
        _sweep_row(f"H={H} 天, 全窗口场景",
                   SimConfig(mode="stochastic", horizon=H, n_scen=None,
                             verbose=False), L, V, price)

    print()
    print("B. 终端条件（H=3，56 天窗口）")
    print(hdr)
    print("  " + "-" * 94)
    for term in ("cyclic", "none"):
        _sweep_row(f"H=3, 终端 {term}",
                   SimConfig(mode="stochastic", horizon=3, n_scen=None,
                             terminal=term, verbose=False), L, V, price)

    print()
    print("C. 场景窗口 W 与场景数 S（H=2，周期终端）")
    print(hdr)
    print("  " + "-" * 94)
    for W in (28, 42, 56, 84, 112):
        _sweep_row(f"H=2, 窗口 {W} 天, 全窗口",
                   SimConfig(mode="stochastic", horizon=HORIZON, n_scen=None,
                             window=W, verbose=False), L, V, price)
    for S in (10, 20, 30, 40):
        _sweep_row(f"H=2, 窗口 56 天, S={S}",
                   SimConfig(mode="stochastic", horizon=HORIZON, n_scen=S,
                             verbose=False), L, V, price)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="只跑敏感性分析")
    ap.add_argument("--horizon", type=int, default=HORIZON)
    args = ap.parse_args(argv)

    _, price, _, _ = load_attachment1()
    dates, L, V = load_attachment2()

    if args.sweep:
        sweep(L, V, price)
        return

    print("=" * 84)
    print("问题2  全年滚动仿真")
    print("=" * 84)
    print(f"  主预测器    : {best_forecaster().name}   (MAE 242.12 kW)")
    print(f"  前瞻天数 H  : {args.horizon}")
    print(f"  场景集      : 决策日前 56 天整日残差，等权，共 56 个场景")
    print(f"  终端条件    : 周期终端（前瞻末端回到前瞻起点电量）")
    print()
    results = run_all(L, V, price, horizon=args.horizon)

    lines, headline = report(results, L, V, price)
    print()
    print("\n".join(lines))

    # ---- 导出 ----
    i0, i1 = REPORT_FROM, L.shape[0]
    r = results["stochastic"]
    sub = type(r)(mode=r.mode, horizon=r.horizon, n_scen=r.n_scen)
    for nm in ("g", "c", "d", "z", "e", "fc", "N", "E_traj"):
        setattr(sub, nm, getattr(r, nm)[i0:i1])
    for nm in ("E_end", "E_start", "plan_cost", "emg_cost"):
        setattr(sub, nm, getattr(r, nm)[i0:i1])

    export_result2(sub, dates[i0:i1], price, OUT / "result2.xlsx")
    export_daily_summary(sub, dates[i0:i1], OUT / "daily_summary.csv")
    export_detail(sub, dates[i0:i1], OUT / "schedule_detail.csv")
    np.savez(OUT / "solution.npz",
             dates=np.array([d.strftime("%Y-%m-%d") for d in dates[i0:i1]]),
             price=price, load=L[i0:i1], pv=V[i0:i1],
             g=r.g[i0:i1], c=r.c[i0:i1], d=r.d[i0:i1], z=r.z[i0:i1],
             e=r.e[i0:i1], fc=r.fc[i0:i1], N=r.N[i0:i1],
             E_start=r.E_start[i0:i1], E_end=r.E_end[i0:i1],
             E_traj=r.E_traj[i0:i1],
             plan_cost=r.plan_cost[i0:i1], emg_cost=r.emg_cost[i0:i1],
             base0=headline["base0"], base1=headline["base1"])
    for mode in ("deterministic", "perfect"):
        rr = results[mode]
        np.savez(OUT / f"solution_{mode}.npz",
                 g=rr.g[i0:i1], c=rr.c[i0:i1], d=rr.d[i0:i1], e=rr.e[i0:i1],
                 plan_cost=rr.plan_cost[i0:i1], emg_cost=rr.emg_cost[i0:i1])
    with open(OUT / "summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "horizon": args.horizon,
            "forecaster": best_forecaster().name,
            "forecaster_spec": list(BEST_SPEC),
            "n_scenarios": 56,
            "report_days": int(i1 - i0),
            "headline": {k: float(v) for k, v in headline.items()},
            "stochastic": summarize(r, i0),
            "deterministic": summarize(results["deterministic"], i0),
            "perfect": summarize(results["perfect"], i0),
        }, f, ensure_ascii=False, indent=2)

    print("\n已导出:")
    for p in ("result2.xlsx", "daily_summary.csv", "schedule_detail.csv",
              "solution.npz", "summary.json"):
        print(f"  {OUT / p}")
    with open(OUT / "report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  {OUT / 'report.txt'}")


if __name__ == "__main__":
    main()
