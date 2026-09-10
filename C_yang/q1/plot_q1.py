"""问题1 结果绘图。

图1  调度结果总览：电价 / 购电量 / 充放电量 + 储电量（共享时间轴，3 面板）
图2  与无储能基线的对比及收益分解
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

SKILL = Path.home() / ".claude" / "skills" / "cumcm-plotting" / "scripts"
sys.path.insert(0, str(SKILL))
from setup_style import setup_style          # noqa: E402
from export_figure import export_figure      # noqa: E402

HERE = Path(__file__).parent
FIGS = HERE / "figs"

# Okabe-Ito 色盲安全配色，含义在全图一致
C_PRICE = "#D55E00"   # 电价
C_GRID = "#0072B2"    # 购电
C_PV = "#E69F00"      # 光伏
C_LOAD = "#444444"    # 负载
C_CHG = "#56B4E9"     # 充电
C_DIS = "#D55E00"     # 放电
C_SOC = "#009E73"     # 储电量


def load_data():
    d = np.load(HERE / "solution.npz", allow_pickle=True)
    out = {k: d[k] for k in ("price", "load", "pv", "g", "c", "d", "w", "E")}
    out["labels"] = [str(x) for x in d["labels"]]
    out["obj_lp"] = float(d["obj_lp"])
    out["base_cost"] = float(d["base_cost"])
    out["hours"] = np.arange(1, len(out["price"]) + 1) / 6.0   # 区间末时刻（小时）
    return out


def _hour_axis(ax):
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.set_xlabel("时刻")


def fig1_dispatch(d):
    setup_style(journal="general", lang="zh")
    fig, axes = plt.subplots(3, 1, figsize=(8.6, 9.2), sharex=True)
    h = d["hours"]
    hl = h - 1 / 12.0            # 柱状量的区间中心

    # ---- (a) 电价 ----
    ax = axes[0]
    ax.step(h, d["price"], where="post", color=C_PRICE, lw=1.4)
    ax.fill_between(h, 0, d["price"], step="post", color=C_PRICE, alpha=0.13)
    ax.axhline(d["price"].mean(), color="grey", ls=":", lw=1.0,
               label=f"全日均价 {d['price'].mean():.3f}")
    ax.set_ylabel("电价 (元/kWh)")
    ax.set_ylim(0, d["price"].max() * 1.22)
    ax.legend(loc="upper left", framealpha=0.9)
    ax.set_title("(a) 分时电价", loc="left")
    for x0, x1, txt in [(6, 9.5, "早高峰"), (17.5, 20.5, "晚高峰")]:
        ax.axvspan(x0, x1, color="grey", alpha=0.12)
        ax.text((x0 + x1) / 2, d["price"].max() * 1.10, txt,
                ha="center", va="top", fontsize=9, color="#333333")

    # ---- (b) 负载 / 光伏 / 购电 ----
    ax = axes[1]
    ax.bar(hl, d["g"], width=1 / 6, color=C_GRID, alpha=0.85, label="计划购电量")
    ax.plot(h, d["load"], color=C_LOAD, lw=1.3, ls="--", label="小区负载")
    ax.plot(h, d["pv"], color=C_PV, lw=1.3, label="光伏发电")
    ax.set_ylabel("电量 (kWh/10min)")
    ax.set_ylim(0, max(d["load"].max(), d["g"].max()) * 1.38)
    ax.legend(loc="upper left", ncol=3, framealpha=0.95, borderpad=0.4,
              columnspacing=1.2, handlelength=1.6)
    ax.set_title("(b) 购电量与源荷曲线", loc="left")

    # ---- (c) 充放电 + 储电量 ----
    ax = axes[2]
    ax.bar(hl, d["c"], width=1 / 6, color=C_CHG, label="充电量")
    ax.bar(hl, -d["d"], width=1 / 6, color=C_DIS, label="放电量")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("充/放电量 (kWh/10min)")
    ax.set_ylim(-d["d"].max() * 1.30, d["c"].max() * 1.42)

    ax2 = ax.twinx()
    ax2.plot(h, d["E"], color=C_SOC, lw=1.8, label="储电量")
    ax2.axhline(1200, color=C_SOC, ls="--", lw=0.9, alpha=0.75)
    ax2.axhline(10800, color=C_SOC, ls="--", lw=0.9, alpha=0.75)
    ax2.text(23.8, 1200, "下限 1200 ", va="bottom", ha="right",
             fontsize=8, color=C_SOC)
    ax2.text(23.8, 10800, "上限 10800 ", va="bottom", ha="right",
             fontsize=8, color=C_SOC)
    ax2.set_ylabel("储电量 (kWh)", color=C_SOC)
    ax2.set_ylim(0, 12600)
    ax2.tick_params(axis="y", colors=C_SOC)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(C_SOC)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower left", ncol=3, framealpha=0.95,
              borderpad=0.4, columnspacing=1.2, handlelength=1.6)
    ax.set_title("(c) 储能充放电与储电量", loc="left")
    _hour_axis(ax)

    fig.suptitle(f"问题1  确定性储能调度最优解   全天购电费 {d['obj_lp']:,.2f} 元",
                 fontsize=13)
    paths = export_figure(fig, str(FIGS / "fig1_dispatch"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


def fig2_comparison(d):
    """基线与优化对照：购电曲线 + 收益分解。"""
    setup_style(journal="general", lang="zh")
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0),
                             gridspec_kw={"width_ratios": [2.05, 1]})

    # ---- 左：两条购电曲线 ----
    ax = axes[0]
    h = d["hours"]
    g_base = np.maximum(d["load"] - d["pv"], 0.0)
    ax.plot(h, g_base, color="#BBBBBB", lw=1.5, label="无储能：直接购电")
    ax.plot(h, d["g"], color=C_GRID, lw=1.5, label="储能在位：优化购电")
    ax.fill_between(h, d["g"], g_base, color="#999999", alpha=0.22,
                    label="购电量削减")
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.set_xlabel("时刻")
    ax.set_ylabel("购电量 (kWh/10min)")
    ax.set_ylim(0, max(g_base.max(), d["g"].max()) * 1.30)
    ax.legend(loc="upper left", framealpha=0.95)
    ax.set_title("(a) 计划购电量对比", loc="left")

    # ---- 右：收益分解（直接标注，不用图例，避免遮挡柱体）----
    ax = axes[1]
    base, opt = d["base_cost"], d["obj_lp"]
    pv_gain, arb_gain = 6727.28, 6197.82
    W = 0.5
    ax.bar([0], [opt], color=C_GRID, width=W)
    ax.bar([0], [pv_gain], bottom=opt, color="#009E73", width=W)
    ax.bar([0], [arb_gain], bottom=opt + pv_gain, color="#CC79A7", width=W)
    ax.bar([1], [base], color="#BBBBBB", width=W)

    seg = [(opt / 2, f"实付购电费\n{opt:,.0f} 元", 9.5),
           (opt + pv_gain / 2, f"光伏余电消纳\n{pv_gain:,.0f} 元", 8.5),
           (opt + pv_gain + arb_gain / 2, f"峰谷价差套利\n{arb_gain:,.0f} 元", 8.5)]
    for y, txt, fs in seg:
        ax.text(0, y, txt, ha="center", va="center",
                fontsize=fs, color="white", fontweight="bold")
    ax.text(1, base / 2, f"无储能基线\n{base:,.0f} 元", ha="center", va="center",
            color="white", fontsize=9.5, fontweight="bold")
    ax.annotate(f"节省 {base - opt:,.0f} 元\n({(base - opt) / base * 100:.2f}%)",
                xy=(0.26, base), xytext=(1.02, base * 1.20),
                ha="center", fontsize=10, color=C_DIS, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=C_DIS, lw=1.2))
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["使用储能（优化调度）", "不使用储能（基线）"])
    ax.set_ylabel("全天购电费 (元)")
    ax.set_ylim(0, base * 1.40)
    ax.set_xlim(-0.5, 1.5)
    ax.set_title("(b) 收益来源分解", loc="left", pad=14)

    fig.suptitle("问题1  储能调度效果与收益分解", fontsize=13, y=1.0)
    paths = export_figure(fig, str(FIGS / "fig2_comparison"),
                          formats=["png", "pdf"], dpi=300)
    plt.close(fig)
    return paths


if __name__ == "__main__":
    FIGS.mkdir(exist_ok=True)
    d = load_data()
    for p in fig1_dispatch(d) + fig2_comparison(d):
        print("已导出:", p)
