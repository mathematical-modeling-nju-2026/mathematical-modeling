"""生成论文用图：Q2 全年费用累积曲线 + 方案对照。"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(r"d:\数学建模大赛\mathematical-modeling")
Q2 = ROOT / "question2" / "results"
OUT = ROOT / "paper" / "figs"
OUT.mkdir(parents=True, exist_ok=True)


def daily(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    return df


# ---- 图：Q2 推荐方案 vs 原口径的逐日累积费用 ----
try:
    rec = daily(Q2 / "recommended_only" / "variants" / "uniform56" / "daily_summary.csv")
except Exception:
    rec = daily(Q2 / "daily_summary.csv")

base_cost = rec["total_cost_yuan"].to_numpy(float)
days = np.arange(1, len(base_cost) + 1)
cum = np.cumsum(base_cost)

fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))

ax = axes[0]
ax.plot(days, cum / 1e4, lw=1.8, color="#1f77b4")
ax.set_xlabel("运行天数")
ax.set_ylabel("累计费用（万元）")
ax.set_title("问题二：全年累计购电费用")
ax.grid(alpha=0.3)
ax.axhline(cum[-1] / 1e4, color="r", ls=":", lw=1)
ax.text(len(days) * 0.55, cum[-1] / 1e4 * 0.93,
        f"全年 {cum[-1]/1e4:.1f} 万元", color="r", fontsize=9)

ax = axes[1]
ax.plot(days, base_cost, lw=0.9, color="#2ca02c", alpha=0.8)
ax.set_xlabel("运行天数")
ax.set_ylabel("当日费用（元）")
ax.set_title("问题二：逐日购电费用")
ax.grid(alpha=0.3)

fig.tight_layout()
fig.savefig(OUT / "q2_trend.pdf", dpi=150)
fig.savefig(OUT / "q2_trend.png", dpi=150)
plt.close(fig)
print("已生成 q2_trend.pdf / .png")
print(f"  天数={len(days)}  全年={cum[-1]/1e4:.2f} 万元  日均={base_cost.mean():.0f} 元")
