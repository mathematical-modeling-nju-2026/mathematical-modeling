"""问题3 图表生成。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

d = np.load(HERE / "_q3_result.npz", allow_pickle=True)
dates = d["dates"]
g_plan = d["g_plan"]; g_final = d["g_final"]
c = d["c"]; dis = d["d"]; e = d["e"]
E_start = d["E_start"]; E_end = d["E_end"]; N = d["N"]; price = d["price"]
DT = 1 / 6
nd = len(dates)


def day_idx(s):
    return int(np.where(dates == s)[0][0])


# ---- 图1：典型日 计划 vs 调整 vs 实际净负载 ----
day = day_idx("2025-09-23")
t = np.arange(144) * 10 / 60
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(t, g_plan[day] / DT, lw=1.6, label="0:00 计划购电 (kW)", color="#1f77b4")
ax.plot(t, g_final[day] / DT, lw=1.6, label="调整后购电 (kW)", color="#2ca02c", ls="--")
ax.plot(t, N[day], lw=1.2, label="实际净负载 (kW)", color="#444", alpha=0.7)
ax.fill_between(t, 0, e[day] / DT, color="#d62728", alpha=0.25, label="紧急购电 (kW)")
ax.set_xlabel("时刻 (h)"); ax.set_ylabel("功率 (kW)")
ax.set_title(f"2025-09-23 计划购电 / 调整购电 / 实际净负载")
ax.legend(loc="upper left", ncol=2, fontsize=9)
ax.grid(alpha=0.3); ax.set_xlim(0, 24)
fig.tight_layout(); fig.savefig(FIG / "fig1_典型日_计划与调整.png", dpi=140); plt.close(fig)

# ---- 图2：储能 SOC 轨迹（典型日）----
Etraj = np.zeros((c.shape[0], 145))
for i in range(c.shape[0]):
    Etraj[i, 0] = E_start[i]
    Etraj[i, 1:] = E_start[i] + np.cumsum(0.9 * c[i] - dis[i] / 0.9)
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(t, Etraj[day, :144], lw=1.8, color="#9467bd")
ax.axhline(1200, color="r", ls=":", lw=1, label="下限 1200 kWh")
ax.axhline(10800, color="r", ls=":", lw=1, label="上限 10800 kWh")
ax.set_xlabel("时刻 (h)"); ax.set_ylabel("储电量 (kWh)")
ax.set_title(f"2025-09-23 储能电量轨迹（0:00 始 {E_start[day]:.0f} kWh，24:00 末 {E_end[day]:.0f} kWh）")
ax.legend(fontsize=9); ax.grid(alpha=0.3); ax.set_xlim(0, 24)
fig.tight_layout(); fig.savefig(FIG / "fig2_储能SOC轨迹.png", dpi=140); plt.close(fig)

# ---- 图3：全月每日购电费构成 ----
pc = np.array([price @ g_plan[i] for i in range(nd)])
ac = np.array([1.5 * (price @ np.maximum(g_final[i] - g_plan[i], 0))
               - 0.5 * (price @ np.maximum(g_plan[i] - g_final[i], 0)) for i in range(nd)])
ec = np.array([5.0 * (price @ e[i]) for i in range(nd)])
x = np.arange(nd)
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.bar(x, pc / 1e4, width=0.8, label="计划购电费", color="#1f77b4")
ax.bar(x, ac / 1e4, width=0.8, bottom=pc / 1e4, label="调整相关费用", color="#ff7f0e")
ax.bar(x, ec / 1e4, width=0.8, bottom=(pc + ac) / 1e4, label="紧急购电费", color="#d62728")
ax.set_xlabel("日期"); ax.set_ylabel("费用 (万元)")
ax.set_title("2025-02-01 ~ 2025-12-31 每日购电费用构成")
step = 15
ax.set_xticks(x[::step]); ax.set_xticklabels([str(dd)[5:] for dd in dates[::step]], rotation=45, fontsize=8)
ax.legend(fontsize=9); ax.grid(alpha=0.3, axis="y")
fig.tight_layout(); fig.savefig(FIG / "fig3_每日费用构成.png", dpi=140); plt.close(fig)

# ---- 图4：调整额度分布（v 调减 / u 调增）----
v_all = np.maximum(g_plan - g_final, 0).sum() * DT
u_all = np.maximum(g_final - g_plan, 0).sum() * DT
fig, ax = plt.subplots(figsize=(6.5, 5))
ax.bar(["调减 (v)", "调增 (u)"], [v_all / 1e4, u_all / 1e4],
       color=["#2ca02c", "#ff7f0e"])
ax.set_ylabel("全年累计电量 (万 kWh)")
ax.set_title(f"调整电量结构（全年）\n调减 {v_all/1e4:.2f} 万 kWh，调增 {u_all/1e4:.2f} 万 kWh")
for i, v in enumerate([v_all / 1e4, u_all / 1e4]):
    ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=11)
fig.tight_layout(); fig.savefig(FIG / "fig4_调整电量结构.png", dpi=140); plt.close(fig)

print("图表已生成：", [p.name for p in sorted(FIG.glob("*.png"))])
