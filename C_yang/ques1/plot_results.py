"""从本目录实际调度结果绘图，导出 300 DPI PNG 和矢量 PDF。"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(HERE / ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from export_figure import export_figure
from setup_style import setup_style


def main():
    style = setup_style(journal="general", lang="zh", use_sciplots=False)
    plt.rcParams.update({"font.size": 10, "axes.labelsize": 10, "axes.titlesize": 11,
                         "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9})
    data = pd.read_csv(HERE / "dispatch_detail.csv")
    summary = json.loads((HERE / "summary.json").read_text(encoding="utf-8"))
    totals, param = summary["totals"], summary["parameters"]
    edges = np.arange(145)/6
    midpoints = (edges[:-1]+edges[1:])/2
    colors = {"grid": "#0072B2", "pv": "#E69F00", "load": "#444444",
              "charge": "#009E73", "discharge": "#D55E00", "state": "#0072B2",
              "price": "#7B3F98", "baseline": "#777777"}
    fig, axes = plt.subplots(5, 1, figsize=(9.2, 11.2), sharex=True,
                             gridspec_kw={"height_ratios": [0.85, 1, 1, 1, 1.1]})
    fig.suptitle("第一问：确定性储能最优调度", fontsize=15)
    ax = axes[0]
    ax.stairs(data.price_yuan_per_kwh, edges, baseline=None, color=colors["price"], linewidth=1.5)
    ax.set_ylabel("电价（元/kWh）")
    ax.set_title("(a) 当天已知电价", loc="left")

    ax = axes[1]
    ax.stairs(data.load_kw, edges, baseline=None, label="小区负载", color=colors["load"], linewidth=1.4)
    ax.stairs(data.pv_kw, edges, baseline=None, label="光伏预测", color=colors["pv"], linewidth=1.5)
    ax.set_ylabel("功率（kW）")
    ax.set_title("(b) 负载与光伏输入", loc="left")
    ax.legend(loc="upper right", frameon=False, ncols=2)
    ax.set_ylim(bottom=0)

    ax = axes[2]
    ax.stairs(data.no_storage_grid_kwh*6, edges, baseline=None, label="无储能购电", color=colors["baseline"],
              linewidth=1.2, linestyle="--")
    ax.stairs(data.grid_kwh*6, edges, baseline=None, label="优化后购电", color=colors["grid"], linewidth=1.5)
    ax.set_ylabel("购电功率（kW）")
    ax.set_title("(c) 从外网购电的时序变化", loc="left")
    ax.legend(loc="upper left", frameon=False, ncols=2)
    ax.set_ylim(bottom=0)

    ax = axes[3]
    ax.bar(midpoints, data.charge_kwh*6, width=1/6, label="充电（正）", color=colors["charge"], alpha=0.9)
    ax.bar(midpoints, -data.discharge_kwh*6, width=1/6, label="放电（负）", color=colors["discharge"], alpha=0.9)
    ax.axhline(0, color="#555555", linewidth=0.6)
    ax.axhline(param["power_max_kw"], color="#999999", linestyle=":", linewidth=0.8)
    ax.axhline(-param["power_max_kw"], color="#999999", linestyle=":", linewidth=0.8)
    ax.set_ylim(-6600, 7200)
    ax.set_ylabel("充放电功率（kW）")
    ax.set_title("(d) 设备外部输入与输出功率", loc="left")
    ax.legend(loc="upper center", frameon=False, ncols=2)

    ax = axes[4]
    energy = np.r_[param["energy_initial_kwh"], data.energy_end_kwh]
    ax.plot(edges, energy, color=colors["state"], linewidth=1.8, label="电池内部储电量")
    ax.axhline(param["energy_max_kwh"], color="#777777", linestyle="--", linewidth=0.8, label="储电量上下限")
    ax.axhline(param["energy_min_kwh"], color="#777777", linestyle="--", linewidth=0.8)
    ax.scatter([0, 24], [energy[0], energy[-1]], color=colors["state"], s=25, zorder=4)
    ax.annotate("日初 6000", (0, 6000), xytext=(6, 8), textcoords="offset points", fontsize=9)
    ax.annotate("日末 6000", (24, 6000), xytext=(-6, 8), textcoords="offset points", ha="right", fontsize=9)
    ax.set_ylabel("储电量（kWh）")
    ax.set_title("(e) 电池状态及日初、日末约束", loc="left")
    ax.set_ylim(0, 12500)
    ax.legend(loc="upper center", ncols=2, frameon=False)
    ax.set_xlabel("时刻（小时）")
    for ax in axes:
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 2))
        ax.grid(axis="y", alpha=0.17)
        ax.set_axisbelow(True)
    export_figure(fig, str(HERE / "figures" / "dispatch_overview"),
                  formats=["png", "pdf"], dpi=300, size_inches=(9.2, 11.2), tight=False)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), gridspec_kw={"width_ratios": [0.85, 1.4]})
    ax = axes[0]
    amounts = np.array([totals["baseline_cost_yuan"], totals["cost_yuan"]])
    bars = ax.bar(["无储能", "优化储能"], amounts/10000, color=[colors["baseline"], colors["grid"]], width=0.55)
    ax.bar_label(bars, labels=[f"{x:,.2f} 元" for x in amounts], padding=6, fontsize=9)
    ax.set_ylim(0, 6.2)
    ax.set_ylabel("全天购电费（万元）")
    ax.set_title("(a) 全天费用比较", loc="left")
    ax.text(0.5, 0.92, f"节省 {totals['saving_percent']:.2f}%", transform=ax.transAxes,
            ha="center", color=colors["grid"], fontsize=12)
    ax.grid(axis="y", alpha=0.17)
    ax.set_axisbelow(True)
    ax = axes[1]
    ax.plot(edges, np.r_[0, data.no_storage_cost_yuan.cumsum()]/10000,
            label="无储能", color=colors["baseline"], linestyle="--", linewidth=1.5)
    ax.plot(edges, np.r_[0, data.cost_yuan.cumsum()]/10000,
            label="优化储能", color=colors["grid"], linewidth=1.8)
    ax.set_xlim(0, 24)
    ax.set_ylim(bottom=0)
    ax.set_xticks(np.arange(0, 25, 4))
    ax.set_xlabel("时刻（小时）")
    ax.set_ylabel("累计购电费（万元）")
    ax.set_title("(b) 累计费用随时间变化", loc="left")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(alpha=0.17)
    export_figure(fig, str(HERE / "figures" / "cost_comparison"),
                  formats=["png", "pdf"], dpi=300, size_inches=(9.2, 3.8), tight=False)
    plt.close(fig)
    print(f"Matplotlib {matplotlib.__version__}; Chinese font: {style['cjk_font']}")


if __name__ == "__main__":
    main()
