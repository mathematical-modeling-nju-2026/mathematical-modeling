"""问题2 结果绘图。

图1  预测与场景集：点预测 / 整日残差场景带 / 实际净负载 + 全年预测误差逐日分布
图2  全年运行：逐日计划购电量与紧急购电量、逐日储电量轨迹
图3  表3 指定日期的调度明细（2025.3.20 / 6.21 / 9.23 / 12.21）
图4  分层收益分解（无储能 / 确定性规划 / 随机规划 / 完美预见）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

SKILL = Path.home() / ".claude" / "skills" / "cumcm-plotting" / "scripts"
sys.path.insert(0, str(SKILL))
from setup_style import setup_style          # noqa: E402
from export_figure import export_figure      # noqa: E402

from q2_data import DT, T, load_attachment1, load_attachment2, net_load
from q2_forecast import best_forecaster
from q2_scenarios import build_scenarios

HERE = Path(__file__).parent
FIGS = HERE / "figs"

C_PRICE = "#D55E00"
C_GRID = "#0072B2"
C_PV = "#E69F00"
C_LOAD = "#444444"
C_ACT = "#000000"
C_FC = "#0072B2"
C_SCEN = "#56B4E9"
C_EMG = "#D55E00"
C_SOC = "#009E73"
C_BASE = "#BBBBBB"

TARGET_DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]

CAP_VIZ = 900.0        # 图5 左栏充放电轴的显示上限（kWh/段，实际上限 833.33）


def load_all():
    d = np.load(HERE / "solution.npz", allow_pickle=True)
    out = {k: d[k] for k in ("price", "load", "pv", "g", "c", "d", "z", "e",
                             "fc", "N", "E_traj", "E_start", "E_end",
                             "plan_cost", "emg_cost")}
    out["dates"] = [str(x) for x in d["dates"]]
    out["base0"] = float(d["base0"])
    out["hours"] = np.arange(1, T + 1) / 6.0
    d2 = np.load(HERE / "solution_deterministic.npz")
    out["g_det"] = d2["g"]
    out["e_det"] = d2["e"]
    dp = np.load(HERE / "solution_perfect.npz")
    out["g_perf"] = dp["g"]
    return out


def _hour_axis(ax):
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.set_xlabel("时刻")


# ---------------- 图1 ----------------

def fig1_forecast():
    setup_style(journal="general", lang="zh")
    dates, L, V = load_attachment2()
    N = net_load(L, V)
    fc = best_forecaster()
    R = fc.residual(L, V)
    FC = fc.matrix(L, V, 0)

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.0),
                             gridspec_kw={"width_ratios": [1.12, 1]})
    h = np.arange(1, T + 1) / 6.0

    # (a) 某日：场景带 + 实际
    ax = axes[0]
    di = dates.index([d for d in dates if d.strftime("%Y-%m-%d") == TARGET_DATES[1]][0])
    sc, w = build_scenarios(R, di, FC[di])
    Nsc = sc * DT
    for k, row in enumerate(Nsc):
        ax.plot(h, row, color=C_SCEN, lw=0.45, alpha=0.35,
                label="历史残差场景（56 条）" if k == 0 else None)
    ax.plot(h, FC[di] * DT, color=C_FC, lw=1.8, label="净负载点预测")
    ax.plot(h, N[di] * DT, color=C_ACT, lw=1.6, ls="--", label="实际净负载")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.set_xlabel("时刻")
    ax.set_ylabel("净负载 (kWh/10min)")
    ax.legend(loc="upper left", framealpha=0.95)
    ax.set_title(f"(a) {TARGET_DATES[1]} 净负载预测与场景集", loc="left")

    # (b) 全年逐日预测误差
    ax = axes[1]
    err = (N - FC)[31:] * DT
    dtot = err.sum(axis=1)
    x = np.arange(len(dtot))
    ax.bar(x, dtot, width=1.0, linewidth=0,
           color=[C_EMG if v > 0 else C_FC for v in dtot], alpha=0.85)
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(dtot.std(), color="grey", ls=":", lw=1.0)
    ax.axhline(-dtot.std(), color="grey", ls=":", lw=1.0)
    ax.set_xlim(0, len(dtot))
    ax.set_xlabel("2025 年日期（2 月 1 日起）")
    ax.set_ylabel("日净负载预测误差 (kWh/日)")
    tick = [i for i, d in enumerate(dates[31:]) if d.day == 1]
    ax.set_xticks(tick)
    ax.set_xticklabels([dates[31:][i].strftime("%m月") for i in tick])
    ax.set_title("(b) 全年逐日预测误差", loc="left")

    fig.suptitle("问题2  净负载预测与残差场景集", fontsize=13)
    paths = export_figure(fig, str(FIGS / "fig1_forecast"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


# ---------------- 图2 ----------------

def fig2_yearly(d):
    setup_style(journal="general", lang="zh")
    dates = d["dates"]
    fig, axes = plt.subplots(2, 1, figsize=(9.4, 6.4), sharex=True)

    x = np.arange(len(dates))
    tick = [i for i, s in enumerate(dates) if s.endswith("-01")]

    ax = axes[0]
    ax.bar(x, d["e"].sum(axis=1), width=1.0, color=C_EMG, alpha=0.9, linewidth=0,
           label="紧急购电量")
    ax.plot(x, d["g"].sum(axis=1), color=C_GRID, lw=1.1, label="计划购电量")
    ax.set_ylabel("日购电量 (kWh)")
    ax.legend(loc="upper left", framealpha=0.95, ncol=2)
    ax.set_title("(a) 逐日计划购电量与紧急购电量", loc="left")

    ax = axes[1]
    ax.fill_between(x, d["E_start"], d["E_end"], color=C_SOC, alpha=0.30,
                    label="日内储电量变化区间")
    ax.plot(x, d["E_end"], color=C_SOC, lw=1.2, label="24:00 储电量")
    ax.axhline(1200, color="grey", ls="--", lw=0.9)
    ax.axhline(10800, color="grey", ls="--", lw=0.9)
    xm = len(dates) * 0.60
    ax.text(xm, 1200, "下限 1200", va="bottom", fontsize=8, color="grey")
    ax.text(xm, 10800, "上限 10800", va="bottom", fontsize=8, color="grey")
    ax.set_ylabel("储电量 (kWh)")
    ax.set_ylim(0, 12600)
    ax.legend(loc="upper left", framealpha=0.95, ncol=2)
    ax.set_title("(b) 逐日储电量轨迹", loc="left")

    axes[1].set_xticks(tick)
    axes[1].set_xticklabels([dates[i][:7] for i in tick])
    axes[1].set_xlabel("日期")
    fig.suptitle("问题2  2025 年全年运行结果", fontsize=13)
    paths = export_figure(fig, str(FIGS / "fig2_yearly"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


# ---------------- 图3 ----------------

def fig3_target_days(d):
    setup_style(journal="general", lang="zh")
    dates = d["dates"]
    idx = [dates.index(s) for s in TARGET_DATES]
    fig, axes = plt.subplots(4, 1, figsize=(9.0, 11.0), sharex=True)
    h = d["hours"]
    hl = h - 1 / 12.0

    for ax, i, lab in zip(axes, idx, TARGET_DATES):
        Nact = (d["load"][i] - d["pv"][i]) * DT
        x = d["g"][i] + d["d"][i] - d["c"][i]
        ax.step(h, d["price"], where="post", color=C_PRICE, lw=1.2, alpha=0.85,
                label="电价")
        ax.set_ylabel("电价 (元/kWh)")
        ax.set_ylim(0, d["price"].max() * 1.18)

        ax2 = ax.twinx()
        # twinx 的坐标区永远画在宿主之上，若不抬升 ax，电价线会被半透明柱遮成一条灰线
        ax.set_zorder(ax2.get_zorder() + 1)
        ax.patch.set_visible(False)
        ax2.bar(hl, x, width=1 / 6, color=C_GRID, alpha=0.75, label="计划净供给",
                linewidth=0)
        ax2.plot(h, Nact, color=C_ACT, lw=1.3, ls="--", label="实际净负载")
        ax2.bar(hl, d["e"][i], width=1 / 6, bottom=x, color=C_EMG, linewidth=0,
                label="紧急购电")
        ax2.set_ylabel("电量 (kWh/10min)")
        # 中午光伏大发时 z 可能为负（储能放电多于购电，净注入电网），必须留出负区
        hi = max(Nact.max(), x.max()) * 1.30
        lo = min(0.0, x.min()) * 1.25
        ax2.set_ylim(lo, hi)
        ax2.axhline(0, color="black", lw=0.7)
        ax2.spines["right"].set_visible(True)

        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax2.legend(h1 + h2, l1 + l2, loc="upper left", ncol=4,
                   framealpha=0.95, fontsize=8, handlelength=1.5,
                   columnspacing=1.0)
        tot = d["e"][i].sum()
        ax.set_title(f"{lab}   紧急购电 {tot:,.0f} kWh   "
                     f"计划购电费 {d['plan_cost'][i]:,.0f} 元", loc="left",
                     fontsize=10)

    _hour_axis(axes[-1])
    fig.suptitle("问题2  表3 指定日期的计划与紧急购电", fontsize=13)
    paths = export_figure(fig, str(FIGS / "fig3_target_days"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


# ---------------- 图4 ----------------

def fig5_storage(d):
    """表3 指定日期的储能充放电与储电量轨迹，直接对应 result2.xlsx 的"充放电量"表。

    左右分栏：左栏给充放电功率（±900 kWh 量级），右栏给储电量（1200–10800 kWh）。
    两者量级相差约 10 倍，共用一根纵轴会把柱子压扁到看不见，故分栏各用各的刻度。
    """
    setup_style(journal="general", lang="zh")
    dates = d["dates"]
    fig, axes = plt.subplots(4, 2, figsize=(10.6, 9.2), sharex=True,
                             gridspec_kw={"width_ratios": [1.25, 1]})
    h = d["hours"]
    hl = h - 1 / 12.0

    for row, lab in zip(axes, TARGET_DATES):
        i = dates.index(lab)
        axP, axE = row

        # ---- 左栏：电价 + 充放电量 ----
        axP.step(h, d["price"], where="post", color=C_PRICE, lw=1.1, alpha=0.85,
                 label="电价")
        axP.set_ylabel("电价 (元/kWh)")
        axP.set_ylim(0, d["price"].max() * 1.18)
        axP.set_xlim(0, 24)
        axP.xaxis.set_major_locator(MultipleLocator(6))

        axP2 = axP.twinx()
        # twinx 的坐标区永远画在宿主之上，若不抬升 axP，电价线会被半透明柱压成灰线
        axP.set_zorder(axP2.get_zorder() + 1)
        axP.patch.set_visible(False)
        lim = CAP_VIZ
        axP2.bar(hl, d["c"][i], width=1 / 6, color=C_FC, alpha=0.8,
                 label="充电量", linewidth=0)
        axP2.bar(hl, -d["d"][i], width=1 / 6, color=C_PV, alpha=0.8,
                 label="放电量", linewidth=0)
        axP2.axhline(0, color="black", lw=0.7)
        axP2.set_ylim(-lim, lim)
        axP2.set_yticks([-CAP_VIZ, 0, CAP_VIZ])
        axP2.set_yticklabels([f"−{CAP_VIZ:,.0f}", "0", f"{CAP_VIZ:,.0f}"])
        axP2.spines["right"].set_visible(True)
        axP2.set_ylabel("充放电量\n(kWh/10min)", fontsize=8)
        axP2.tick_params(axis="y", labelsize=8)

        # ---- 右栏：储电量轨迹 ----
        # E_traj 是各时段**末端**储电量，前面补上当日 0:00 的起始电量，共 145 点
        axE.plot(np.r_[0, h], np.r_[d["E_start"][i], d["E_traj"][i]],
                 color=C_SOC, lw=1.8, label="储电量")
        axE.fill_between(np.r_[0, h], 1200,
                         np.r_[d["E_start"][i], d["E_traj"][i]],
                         color=C_SOC, alpha=0.15)
        axE.axhline(1200, color="grey", ls="--", lw=0.9)
        axE.axhline(10800, color="grey", ls="--", lw=0.9)
        axE.text(0.3, 1200, "下限 1200", va="bottom", fontsize=7, color="grey")
        axE.text(0.3, 10800, "上限 10800", va="bottom", fontsize=7, color="grey")
        axE.set_ylim(0, 12600)
        axE.set_yticks([0, 3000, 6000, 9000, 12000])
        axE.set_ylabel("储电量 (kWh)", fontsize=9)
        axE.tick_params(axis="y", labelsize=8)
        axE.set_xlim(0, 24)
        axE.xaxis.set_major_locator(MultipleLocator(6))
        axE.set_title(f"{lab}  日充 {d['c'][i].sum():,.0f} kWh / "
                      f"日放 {d['d'][i].sum():,.0f} kWh",
                      loc="left", fontsize=9)

        if row is axes[0]:
            h1, l1 = axP.get_legend_handles_labels()
            h2, l2 = axP2.get_legend_handles_labels()
            axP2.legend(h1 + h2, l1 + l2, loc="upper left", ncol=3,
                        framealpha=0.95, fontsize=7.5, handlelength=1.3,
                        columnspacing=0.8)

    for ax in axes[-1]:
        ax.set_xlabel("时刻")
    fig.suptitle("问题2  指定日期的储能充放电与储电量轨迹", fontsize=13)
    paths = export_figure(fig, str(FIGS / "fig5_storage"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


def fig4_decomposition(d):
    setup_style(journal="general", lang="zh")
    fig, ax = plt.subplots(figsize=(9.6, 4.5))

    import json
    with open(HERE / "summary.json", encoding="utf-8") as f:
        S = json.load(f)["headline"]
    base0, base1 = S["base0"], S["base1"]
    b2, b3, b4 = S["b2"], S["b3"], S["b4"]

    names = ["B0\n无储能\n完美预见", "B1\n无储能\n按预测计划",
             "B2\n有储能\n确定性规划", "B3\n有储能\n随机规划\n(主模型)",
             "B4\n有储能\n完美预见"]
    vals = [base0, base1, b2, b3, b4]
    cols = [C_BASE, "#999999", "#E69F00", C_GRID, C_SOC]
    bars = ax.bar(range(5), vals, color=cols, width=0.62, linewidth=0)
    for i, (b, v) in enumerate(zip(bars, vals)):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v / 1e4:,.1f} 万元",
                ha="center", va="bottom", fontsize=9,
                fontweight="bold" if i == 3 else "normal")
    ax.set_xticks(range(5))
    ax.set_xticklabels(names, fontsize=8.5)
    ax.set_ylabel("结算期总购电费 (元)")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.set_xlim(-0.6, 5.9)

    # 两个价值箭头都画在柱子**之间或外侧**的空档，标签一律带白底，
    # 避免与柱顶的金额标签叠在一起（早先的版本正是栽在这里）。
    ax.annotate("", xy=(4.42, b4), xytext=(4.42, base0),
                arrowprops=dict(arrowstyle="<->", color=C_SOC, lw=1.3))
    ax.text(4.52, (base0 + b4) / 2,
            f"储能价值\n(B0−B4)\n{(base0 - b4) / 1e4:,.1f} 万元",
            fontsize=8.5, color=C_SOC, va="center", ha="left")

    ax.annotate("", xy=(3.5, b3), xytext=(3.5, b4),
                arrowprops=dict(arrowstyle="<->", color=C_EMG, lw=1.3))
    ax.text(3.5, b4 * 0.52,
            f"预测不确定性损失\n(B3−B4)\n{abs(b4 - b3) / 1e4:,.1f} 万元",
            fontsize=8.5, color=C_EMG, va="center", ha="center",
            bbox=dict(fc="white", ec="none", alpha=0.88, pad=2.0))

    ax.text(2.5, b4 * 0.52,
            f"随机建模价值\n(B2−B3)\n{(b2 - b3) / 1e4:,.1f} 万元",
            fontsize=8.5, color="#555555", va="center", ha="center",
            bbox=dict(fc="white", ec="none", alpha=0.88, pad=2.0))

    ax.set_title("问题2  分层收益分解（结算期 2025.2.1–12.31）", loc="left")
    paths = export_figure(fig, str(FIGS / "fig4_decomposition"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


if __name__ == "__main__":
    FIGS.mkdir(exist_ok=True)
    d = load_all()
    for p in (fig1_forecast() + fig2_yearly(d) + fig3_target_days(d)
              + fig4_decomposition(d) + fig5_storage(d)):
        print("已导出:", p)
