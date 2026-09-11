"""Plot actual Q2 backtest CSV outputs in PNG (300 dpi) and vector PDF.

No simulation or forecasts are generated here. Energy data are aggregated by
method/month for cost comparisons and converted to ten-minute mean MW only
for the dispatch power panels. The physical time axis is 00:00 through 24:00.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

from setup_style import setup_style
from export_figure import export_figure

METHODS = ("stochastic_48h", "deterministic_48h", "no_storage", "stochastic_24h")
LABELS = {
    "stochastic_48h": "随机48小时（主方案）",
    "deterministic_48h": "确定性48小时（基线）",
    "no_storage": "无储能（基线）",
    "stochastic_24h": "随机24小时（敏感性）",
}
METHOD_COLORS = ("#205C84", "#D08635", "#777E86", "#538E7B")
PLAN, EMERGENCY = "#327AA3", "#D45E42"
CHARGE, DISCHARGE, ENERGY = "#C79535", "#37816A", "#425F99"
SPECIFIED_DATES = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _vector(rows: list[dict], field: str) -> np.ndarray:
    values = np.asarray([float(row[field]) for row in rows])
    if not np.isfinite(values).all():
        raise ValueError(f"Nonfinite plotting data in {field}")
    return values


def _finish(fig, output: Path, name: str, size: tuple[float, float]) -> None:
    export_figure(fig, str(output / name), formats=("png", "pdf"),
                  dpi=300, size_inches=size, tight=False)
    plt.close(fig)


def cost_comparison(daily: list[dict], output: Path) -> None:
    groups = {method: sorted([r for r in daily if r["method"] == method], key=lambda r: r["date"])
              for method in METHODS}
    reference_dates = [r["date"] for r in groups[METHODS[0]]]
    if len(reference_dates) != 334 or any([r["date"] for r in rows] != reference_dates for rows in groups.values()):
        raise ValueError("Cost comparison requires the same 334 February-December days for every method")
    planned = np.array([_vector(groups[m], "planned_cost_yuan").sum() for m in METHODS]) / 1e4
    emergency = np.array([_vector(groups[m], "emergency_cost_yuan").sum() for m in METHODS]) / 1e4
    total = planned + emergency
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.6))
    fig.subplots_adjust(left=0.16, right=0.985, bottom=0.16, top=0.79, wspace=0.27)
    ax = axes[0]
    y = np.arange(len(METHODS))
    ax.barh(y, planned, color=PLAN, height=0.57, label="计划购电费")
    ax.barh(y, emergency, left=planned, color=EMERGENCY, height=0.57,
            hatch="///", linewidth=0, label="紧急购电费")
    for pos, value in enumerate(total):
        ax.text(value + total.max() * 0.018, pos, f"{value:,.2f}", ha="left", va="center", fontsize=9)
    ax.set_yticks(y, [LABELS[m] for m in METHODS])
    ax.invert_yaxis()
    ax.set_xlim(0, float(total.max()) * 1.19)
    ax.set_xlabel("2—12月总购电费 / 万元")
    ax.set_title("(a) 同期费用及构成", loc="left", pad=40)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2, frameon=False,
              columnspacing=1.4, borderaxespad=0)
    ax.grid(axis="x", color="#E4E6E8", linewidth=0.6)
    ax.set_axisbelow(True)
    ax = axes[1]
    months = np.arange(2, 13)
    styles = ("-", "--", ":", "-.")
    markers = ("o", "s", "^", "D")
    for m, color, style, marker in zip(METHODS, METHOD_COLORS, styles, markers):
        monthly = [sum(float(r["total_cost_yuan"]) for r in groups[m] if int(r["date"][5:7]) == month) / 1e4
                   for month in months]
        ax.plot(months, monthly, color=color, linestyle=style, marker=marker,
                markersize=3.5, linewidth=1.4 if m == METHODS[0] else 1.1, label=LABELS[m])
    ax.set_xticks(months)
    ax.set_xlabel("月份")
    ax.set_ylabel("当月总购电费 / 万元")
    ax.set_title("(b) 月度费用变化", loc="left", pad=40)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2, frameon=False,
              columnspacing=1.0, handlelength=2.0, fontsize=8, borderaxespad=0)
    ax.grid(color="#E4E6E8", linewidth=0.6)
    fig.suptitle("第二问：2025年2—12月顺序回测费用", y=0.985, fontsize=13)
    _finish(fig, output, "cost_comparison", (11.6, 4.6))


def dispatch_selected_days(detail: list[dict], output: Path) -> None:
    groups = {day: sorted([r for r in detail if r["date"] == day], key=lambda r: int(r["period"]))
              for day in SPECIFIED_DATES}
    for day, rows in groups.items():
        if len(rows) != 144 or len({r["period"] for r in rows}) != 144:
            raise ValueError(f"Expected all 144 unique intervals for {day}")
    edges = np.arange(145) / 6.0
    fig, axes = plt.subplots(4, 3, figsize=(12.0, 10.5), sharex=True, sharey="col")
    fig.subplots_adjust(left=0.085, right=0.985, bottom=0.07, top=0.87, hspace=0.29, wspace=0.24)
    max_grid = max(max(float(r["grid_plan_kwh"]), float(r["emergency_kwh"])) for rows in groups.values() for r in rows) * 0.006
    for row_number, day in enumerate(SPECIFIED_DATES):
        rows = groups[day]
        plan = _vector(rows, "grid_plan_kwh") * 0.006
        emergency = _vector(rows, "emergency_kwh") * 0.006
        charge = _vector(rows, "charge_kwh") * 0.006
        discharge = _vector(rows, "discharge_kwh") * 0.006
        energy = np.r_[float(rows[0]["energy_start_kwh"]), _vector(rows, "energy_end_kwh")] / 1000
        ax = axes[row_number, 0]
        ax.stairs(plan, edges, baseline=None, color=PLAN, linewidth=1.05)
        ax.stairs(emergency, edges, baseline=None, color=EMERGENCY, linewidth=0.85)
        ax.set_ylim(-0.03 * max_grid, 1.08 * max_grid)
        ax.set_ylabel(day[5:].replace("-", "月") + "日\n购电功率 / MW", labelpad=7)
        ax = axes[row_number, 1]
        ax.fill_between(edges, np.r_[charge, charge[-1]], step="post", color=CHARGE, alpha=0.20)
        ax.fill_between(edges, -np.r_[discharge, discharge[-1]], step="post", color=DISCHARGE, alpha=0.20)
        ax.stairs(charge, edges, baseline=None, color=CHARGE, linewidth=1.05)
        ax.stairs(-discharge, edges, baseline=None, color=DISCHARGE, linewidth=1.05)
        ax.axhline(0, color="#737B80", linewidth=0.6)
        ax.set_ylim(-5.5, 5.5)
        ax.set_yticks([-5, 0, 5])
        ax.set_ylabel("充放电功率 / MW")
        ax = axes[row_number, 2]
        ax.axhspan(1.2, 10.8, color=ENERGY, alpha=0.045)
        ax.axhline(1.2, color="#999999", linestyle="--", linewidth=0.75)
        ax.axhline(10.8, color="#999999", linestyle="--", linewidth=0.75)
        ax.plot(edges, energy, color=ENERGY, linewidth=1.25)
        ax.set_ylim(0, 12)
        ax.set_yticks([0, 3, 6, 9, 12])
        ax.set_ylabel("储电量 / MWh")
        for ax in axes[row_number]:
            ax.set_xlim(0, 24)
            ax.set_xticks([0, 4, 8, 12, 16, 20, 24])
            ax.grid(color="#E5E7E9", linewidth=0.55)
            ax.set_axisbelow(True)
    for ax in axes[-1]:
        ax.set_xlabel("时刻 / h")
    titles = ("(a) 计划与紧急购电", "(b) 充电为正，放电为负", "(c) 电池储电量及运行范围")
    for ax, title in zip(axes[0], titles):
        ax.set_title(title, fontsize=11, pad=43)
    legends = (
        [Line2D([], [], color=PLAN, label="计划购电"), Line2D([], [], color=EMERGENCY, label="紧急购电")],
        [Patch(facecolor=CHARGE, alpha=0.6, label="充电"), Patch(facecolor=DISCHARGE, alpha=0.6, label="放电")],
        [Line2D([], [], color=ENERGY, label="储电量"), Line2D([], [], color="#999999", linestyle="--", label="上下限")],
    )
    for ax, handles in zip(axes[0], legends):
        ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.015),
                  ncol=2, frameon=False, columnspacing=1.3, fontsize=9)
    fig.suptitle("第二问：四个指定日的储能与购电调度", y=0.985, fontsize=14)
    fig.text(0.5, 0.953, "随机优化 · 48小时滚动计划；每10分钟电量换算为该时段平均功率",
             ha="center", va="center", fontsize=10, color="#555555")
    _finish(fig, output, "dispatch_selected_days", (12.0, 10.5))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    output = args.output_dir or args.input_dir / "figures"
    output.mkdir(parents=True, exist_ok=True)
    print(setup_style(journal="general", lang="zh", use_sciplots=False, constrained_layout=False))
    daily = read_csv(args.input_dir / "daily_summary.csv")
    detail = read_csv(args.input_dir / "dispatch_detail.csv")
    cost_comparison(daily, output)
    dispatch_selected_days(detail, output)


if __name__ == "__main__":
    main()
