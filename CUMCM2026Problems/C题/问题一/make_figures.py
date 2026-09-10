"""
问题 1 论文图表（本地确定性绘图，科研风）
图1: 电价、小区负载、光伏预测功率曲线
图2: 储能 SOC 轨迹 + 充放电功率
图3: 全天分时段购电量 + 与无储能基准对比
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT_DIR = Path(r"d:\数学建模大赛\math-modeling-skill\output\c2026_q1")
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)

sol = np.load(OUT_DIR / "q1_solution.npz", allow_pickle=True)
g = sol["g"]; ch = sol["ch"]; dis = sol["dis"]; S = sol["S"]
p = sol["p"]; L = sol["L"]; PV = sol["PV"]
times = list(sol["times"])
cost = float(sol["cost"]); total = float(sol["total_purchase_kwh"])
N = len(g)
DT = 1.0 / 6.0

# x 轴：小时（0..24）
x_hours = (np.arange(N) + 1) * DT
xticks = np.arange(0, 25, 2)

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial"],
    "axes.unicode_minus": False,
    "figure.dpi": 150,
})

# ---------------- 图 1: 电价 / 负载 / 光伏 ----------------
fig, ax1 = plt.subplots(figsize=(9, 4.2))
ax1.plot(x_hours, L, color="#d62728", lw=1.4, label="小区负载 (kW)")
ax1.plot(x_hours, PV, color="#2ca02c", lw=1.4, label="光伏预测功率 (kW)")
ax1.set_xlabel("时间 (h)")
ax1.set_ylabel("功率 (kW)")
ax1.set_xlim(0, 24)
ax1.set_xticks(xticks)
ax1.grid(alpha=0.3)

ax2 = ax1.twinx()
ax2.plot(x_hours, p, color="#1f77b4", lw=1.2, ls="--", label="电价 (元/kWh)")
ax2.set_ylabel("电价 (元/kWh)", color="#1f77b4")
ax2.tick_params(axis="y", labelcolor="#1f77b4")

h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
ax1.set_title("图 1  代表日电价、小区负载与光伏预测功率曲线")
fig.tight_layout()
fig.savefig(FIG_DIR / "fig1_price_load_pv.png")
plt.close(fig)

# ---------------- 图 2: SOC 轨迹 + 充放电功率 ----------------
S_all = np.concatenate([[6000.0], S])   # 0:00 到 24:00 共 N+1 个点
xs = np.arange(N + 1) * DT

fig, ax1 = plt.subplots(figsize=(9, 4.2))
ax1.plot(xs, S_all, color="#9467bd", lw=1.8, label="储能电量 SOC (kWh)")
ax1.axhline(10800, color="gray", ls=":", lw=1)
ax1.axhline(1200, color="gray", ls=":", lw=1)
ax1.fill_between(xs, 1200, 10800, color="gray", alpha=0.06)
ax1.set_xlabel("时间 (h)")
ax1.set_ylabel("储能电量 (kWh)", color="#9467bd")
ax1.tick_params(axis="y", labelcolor="#9467bd")
ax1.set_xlim(0, 24)
ax1.set_xticks(xticks)
ax1.set_ylim(0, 12000)
ax1.grid(alpha=0.3)

ax2 = ax1.twinx()
ax2.bar(x_hours - DT / 2, ch, width=DT * 0.8, color="#2ca02c", alpha=0.55, label="充电功率 (kW)")
ax2.bar(x_hours - DT / 2, -dis, width=DT * 0.8, color="#d62728", alpha=0.55, label="放电功率 (kW)")
ax2.set_ylabel("充放电功率 (kW)")
ax2.set_ylim(-6000, 6000)
ax2.axhline(0, color="k", lw=0.6)

h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="lower right", fontsize=8)
ax1.set_title("图 2  储能电量轨迹与充放电功率（0:00 与 24:00 均为 6000 kWh）")
fig.tight_layout()
fig.savefig(FIG_DIR / "fig2_soc_charge_discharge.png")
plt.close(fig)

# ---------------- 图 3: 购电量 + 无储能基准 ----------------
g_kwh = g * DT
# 无储能基准：光伏不够的部分全部购电，光伏过剩时不可上网（本题未提及上网，按弃光处理）
residual = L - PV
base_g = np.maximum(residual, 0.0)
base_cost = float((base_g * p * DT).sum())

fig, ax = plt.subplots(figsize=(9, 4.2))
ax.bar(x_hours - DT / 2, g_kwh, width=DT * 0.85, color="#1f77b4", alpha=0.85, label="计划购电量 (kWh)")
ax.plot(x_hours, L * DT, color="#d62728", lw=1.2, ls="--", label="负载需求 (kWh)")
ax.set_xlabel("时间 (h)")
ax.set_ylabel("电量 (kWh/时段)")
ax.set_xlim(0, 24)
ax.set_xticks(xticks)
ax.grid(alpha=0.3)
ax.legend(fontsize=8)
ax.set_title(f"图 3  全天计划购电量分布（储能方案购电费 {cost:,.0f} 元 vs 无储能 {base_cost:,.0f} 元）")
fig.tight_layout()
fig.savefig(FIG_DIR / "fig3_purchase_distribution.png")
plt.close(fig)

print("图已保存:", [f.name for f in sorted(FIG_DIR.glob('*.png'))])
print(f"无储能基准购电费: {base_cost:,.2f} 元, 购电量: {base_g.sum()*DT:,.2f} kWh")
print(f"储能方案购电费  : {cost:,.2f} 元, 购电量: {total:,.2f} kWh")
print(f"节省: {base_cost - cost:,.2f} 元 ({(base_cost-cost)/base_cost*100:.2f}%)")
