"""问题2 最优方案（1439 万）论文图表。

图1 预测与场景：点预测 / 残差场景带 / 实际净负载（季节代表日）
图2 全年运行：逐日计划购电与紧急购电、储电量轨迹
图3 指定日期调度明细（3.20 / 6.21 / 9.23 / 12.21）
图4 分层收益分解（无储能 / 确定性 / 随机规划 / 完美预见）
图5 储能运行：SOC 轨迹与充放电、紧急购电分布
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial"],
    "font.size": 9,
    "axes.unicode_minus": False,
    "figure.dpi": 150,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

C_PLAN = "#1f77b4"
C_EMG = "#d62728"
C_SOC = "#2ca02c"
C_ACT = "#333333"
C_FC = "#ff7f0e"
C_SCEN = "#9ecae1"
TARGET = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]


def _hours():
    return np.arange(1, 145) / 6.0


def _day_index(dates, s):
    for i, d in enumerate(dates):
        if d.strftime("%Y-%m-%d") == s:
            return i
    return None


def make_all_figures(outdir: Path, g, e, c, d, z, Etraj, E_start, E_end,
                     plan_cost, emg_cost, N, FC, price, dates, summary,
                     R, L, V):
    fig_dir = Path(outdir) / "figures"
    fig_dir.mkdir(exist_ok=True)
    DT = 1 / 6.0
    hrs = _hours()
    n = len(dates)

    # ---------- 图1 预测与场景（选 9.23 为代表日）----------
    di = _day_index(dates, "2025-09-23")
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    lo = di
    Rw = R[max(0, lo - 56):lo]
    ok = ~np.isnan(Rw).any(axis=1)
    Rw = Rw[ok]
    if len(Rw):
        scen = FC[di][None, :] + Rw * DT
        ax.fill_between(hrs, np.percentile(scen, 10, axis=0),
                        np.percentile(scen, 90, axis=0),
                        color=C_SCEN, alpha=0.5, label="残差场景带 (10–90%)")
        ax.plot(hrs, np.median(scen, axis=0), color=C_FC, lw=1.2,
                label="场景中位数")
    ax.plot(hrs, N[di] * DT, color=C_ACT, lw=1.4, label="实际净负载")
    ax.plot(hrs, FC[di], color=C_PLAN, lw=1.2, ls="--", label="点预测")
    ax.set_xlim(0, 24); ax.xaxis.set_major_locator(MultipleLocator(4))
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("净负载 (kWh/10min)")
    ax.set_title("图1  净负载预测与残差场景集（2025-09-23）")
    ax.legend(fontsize=7.5, ncol=2)
    fig.tight_layout(); fig.savefig(fig_dir / "fig1_forecast_scenarios.png"); plt.close(fig)

    # ---------- 图2 全年运行 ----------
    xs = np.arange(n)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.6, 5.2), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1]})
    a1.bar(xs, g.sum(axis=1), color=C_PLAN, alpha=0.85, label="计划购电量")
    a1.bar(xs, e.sum(axis=1), bottom=g.sum(axis=1), color=C_EMG, alpha=0.9,
           label="紧急购电量")
    a1.set_ylabel("购电量 (kWh/日)")
    a1.set_title("图2  全年逐日购电量与储能运行（2025-02-01 ~ 12-31）")
    a1.legend(fontsize=8)
    a2.plot(xs, E_start, color=C_SOC, lw=1.1, label="0:00 储电量")
    a2.plot(xs, E_end, color="#9467bd", lw=1.1, ls="--", label="24:00 储电量")
    a2.axhline(1200, color="gray", ls=":", lw=0.8)
    a2.axhline(10800, color="gray", ls=":", lw=0.8)
    a2.set_ylabel("储电量 (kWh)"); a2.set_xlabel("日期序号（2 月起）")
    a2.legend(fontsize=8, ncol=2)
    step = max(1, n // 12)
    a2.set_xticks(xs[::step])
    a2.set_xticklabels([dates[i].strftime("%m-%d") for i in range(0, n, step)],
                       rotation=0, fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "fig2_yearly.png"); plt.close(fig)

    # ---------- 图3 指定日期调度 ----------
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 5.6))
    for ax, sd in zip(axes.ravel(), TARGET):
        k = _day_index(dates, sd)
        if k is None:
            continue
        ax.bar(hrs, g[k], width=DT, color=C_PLAN, label="计划购电")
        ax.bar(hrs, e[k], width=DT, bottom=g[k], color=C_EMG, label="紧急购电")
        ax.plot(hrs, N[k] * DT, color=C_ACT, lw=1.0, label="实际净负载")
        ax.plot(hrs, z[k], color="#2ca02c", lw=1.0, ls="--", label="计划净供给")
        ax.set_xlim(0, 24); ax.xaxis.set_major_locator(MultipleLocator(6))
        ax.set_title(sd, fontsize=9)
        ax.set_xlabel("时刻 (h)"); ax.set_ylabel("kWh/10min")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("图3  四个指定日期的调度明细", fontsize=11)
    fig.tight_layout(); fig.savefig(fig_dir / "fig3_target_days.png"); plt.close(fig)

    # ---------- 图4 分层收益分解 ----------
    b0 = summary.get("baseline_b0", None)
    b1 = summary.get("baseline_b1", None)
    b2 = summary.get("baseline_b2", None)
    b4 = summary.get("baseline_b4", None)
    total = summary["total_cost_yuan"]
    labels, vals, colors = [], [], []
    for lab, val, col in [("B0 无储能·完美预见", b0, "#cccccc"),
                          ("B1 无储能·按预测计划", b1, "#9ecae1"),
                          ("B2 有储能·确定性规划", b2, "#6baed6"),
                          ("B3 有储能·随机规划（本方案）", total, "#2171b5"),
                          ("B4 有储能·完美预见（下界）", b4, "#08306b")]:
        if val is not None:
            labels.append(lab); vals.append(val / 1e4); colors.append(col)
    if vals:
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
        bars = ax.barh(labels[::-1], vals[::-1], color=colors[::-1])
        for b, v in zip(bars, vals[::-1]):
            ax.text(v, b.get_y() + b.get_height() / 2, f" {v:,.1f} 万",
                    va="center", fontsize=8)
        ax.set_xlabel("总购电费（万元）")
        ax.set_title("图4  分层收益分解")
        fig.tight_layout(); fig.savefig(fig_dir / "fig4_decomposition.png"); plt.close(fig)

    # ---------- 图5 储能与紧急购电 ----------
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.6, 3.2))
    a1.plot(hrs, Etraj[_day_index(dates, "2025-09-23")], color=C_SOC, lw=1.3)
    a1.axhline(1200, color="gray", ls=":", lw=0.8)
    a1.axhline(10800, color="gray", ls=":", lw=0.8)
    a1.set_xlim(0, 24); a1.xaxis.set_major_locator(MultipleLocator(6))
    a1.set_xlabel("时刻 (h)"); a1.set_ylabel("储电量 (kWh)")
    a1.set_title("日内储能轨迹（2025-09-23）", fontsize=9)
    a2.hist(e.flatten(), bins=40, color=C_EMG, alpha=0.85)
    a2.set_xlabel("紧急购电量 (kWh/10min)")
    a2.set_ylabel("频次")
    a2.set_title("紧急购电量分布（全年逐时段）", fontsize=9)
    fig.suptitle("图5  储能运行与紧急购电特征", fontsize=11)
    fig.tight_layout(); fig.savefig(fig_dir / "fig5_storage_emergency.png"); plt.close(fig)
