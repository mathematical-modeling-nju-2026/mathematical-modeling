"""
生成 result1.xlsx（严格遵循附件5模板）与论文图表。

result1.xlsx 模板的"计划购电量"工作表是环形排列：第1行标签 0:10-0:20 ... 第143行
23:50-0:00+1，第144行 0:00+1-0:10+1。因此模板行 i (1-based) 对应附件1时段：
    idx = i % 144  （i=1..143 -> 时段2..144, i=144 -> 时段1）
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ATTACH_DIR = Path(r"d:\数学建模大赛\CUMCM2026Problems\C题\附件")
OUT_DIR = Path(r"d:\数学建模大赛\math-modeling-skill\output\c2026_q1")
DT = 1.0 / 6.0

# 读回求解结果
sol = np.load(OUT_DIR / "q1_solution.npz", allow_pickle=True)
g = sol["g"]; ch = sol["ch"]; dis = sol["dis"]; S = sol["S"]
p = sol["p"]; L = sol["L"]; PV = sol["PV"]
times = list(sol["times"])
cost = float(sol["cost"]); total = float(sol["total_purchase_kwh"])
N = len(g)

# ================= result1.xlsx =================
tpl = ATTACH_DIR / "附件5" / "result1.xlsx"

# 计划购电量：直接套用模板的行标签，按环形映射填值
plan = pd.read_excel(tpl, sheet_name="计划购电量")
assert len(plan) == 144, len(plan)
plan_vals = np.zeros(144)
for i in range(144):          # i: 0-based 行号
    idx = (i + 1) % 144       # 模板行1 -> 附件1时段1 (0-based); 行144 -> 时段0
    plan_vals[i] = g[idx] * DT
plan["购电量"] = plan_vals.round(4)

# 充放电量
cd = pd.read_excel(tpl, sheet_name="充放电量")
seg_groups = [
    ("0:00-4:00", 0, 24), ("4:00-8:00", 24, 48), ("8:00-12:00", 48, 72),
    ("12:00-16:00", 72, 96), ("16:00-20:00", 96, 120), ("20:00-24:00", 120, 144),
]
for r, (lbl, a, b) in enumerate(seg_groups):
    cd.at[r, "充电量"] = round(float(ch[a:b].sum() * DT), 4)
    cd.at[r, "放电量"] = round(float(dis[a:b].sum() * DT), 4)
cd.at[0, "储电量"] = 6000.0      # 0:00
cd.at[1, "储电量"] = round(float(S[-1]), 4)  # 24:00

with pd.ExcelWriter(OUT_DIR / "result1.xlsx") as w:
    plan.to_excel(w, sheet_name="计划购电量", index=False)
    cd.to_excel(w, sheet_name="充放电量", index=False)

print("result1.xlsx 已生成")
print(plan.head(6).to_string())
print(plan.tail(4).to_string())
print(cd.to_string())
