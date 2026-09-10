"""
2026 C 题 问题 1：微网日度计划购电策略（线性规划，含弃光变量）

在每天 0:00，已知当天电价 p_t、小区负载 L_t、光伏预测功率 PV_t（均为 10min 时段，
全天 144 段），储能设备参数见附录 1，要求：
  - 微网供电不低于负载；
  - 储能 0:00 与 24:00 储电量相同；
  - 最小化全天购电费。

决策变量（5 类，共 5N = 720 个连续变量）：
  g_t    : 购电功率 (kW)           [N 个]
  c_t    : 储能充电功率 (kW)        [N 个]
  d_t    : 储能放电功率 (kW)        [N 个]
  S_t    : 时段 t 末储能电量 (kWh)   [N 个]  —— 状态变量
  zeta_t : 弃光功率 (kW)            [N 个]  —— 松弛变量，吸收光伏过剩

模型：
  min  Σ_t p_t * g_t * Δt,  Δt = 1/6 h
  s.t. g_t + PV_t + d_t - c_t - zeta_t = L_t          (功率平衡, 144)
       S_t - S_{t-1} - η*c_t*Δt + d_t*Δt/η = 0       (SOC 演化, 144)
       1200 <= S_t <= 10800                           (电量安全, 288)
       0 <= c_t <= 5000,  0 <= d_t <= 5000            (功率上限, 288)
       g_t >= 0, zeta_t >= 0                          (弃光允许)
       S_144 = S_0 = 6000                             (周期平衡)

说明：zeta_t >= 0 使功率平衡恒可行；目标不惩罚弃光，因此最优解仅在硬约束下才弃光。
对附件 1 数据，诊断显示 PV 过剩可被储能完全吸收，故最优 zeta_t = 0，结果不变。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

# ---------- 参数 ----------
ATTACH_DIR = Path(r"d:\数学建模大赛\CUMCM2026Problems\C题\附件")
OUT_DIR = Path(r"d:\数学建模大赛\math-modeling-skill\output\c2026_q1")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DT = 1.0 / 6.0          # 每时段 10 分钟 = 1/6 小时
ETA = 0.9               # 充放电效率
S_MIN, S_MAX = 1200.0, 10800.0
P_LIM = 5000.0          # 最大充放电功率 kW
S0 = 6000.0             # 初始电量（2025-01-01 0:00）kWh

# ---------- 读取附件 1 ----------
df1 = pd.read_excel(ATTACH_DIR / "附件1.xlsx")
p = df1["电价"].to_numpy(dtype=float)         # 元/kWh
L = df1["小区负载"].to_numpy(dtype=float)     # kW
PV = df1["光伏发电预测功率"].to_numpy(dtype=float)  # kW
times = df1["时间"].astype(str).tolist()
N = len(p)  # 144

# ---------- 构建线性规划 ----------
# 变量顺序: x = [g(0..N-1), c(0..N-1), d(0..N-1), S(0..N-1), zeta(0..N-1)]
n_g = n_c = n_d = n_s = n_z = N
nvar = n_g + n_c + n_d + n_s + n_z

def gi(t):   return t
def ci(t):   return n_g + t
def di(t):   return n_g + n_c + t
def si(t):   return n_g + n_c + n_d + t
def zi(t):   return n_g + n_c + n_d + n_s + t

# 目标: min Σ p_t g_t Δt
c_obj = np.zeros(nvar)
for t in range(N):
    c_obj[gi(t)] = p[t] * DT

# ---- 等式约束 ----
A_eq_rows, b_eq_rows = [], []

# 功率平衡: g_t + d_t - c_t - zeta_t = L_t - PV_t
for t in range(N):
    row = np.zeros(nvar)
    row[gi(t)] = 1.0
    row[ci(t)] = -1.0
    row[di(t)] = 1.0
    row[zi(t)] = -1.0
    A_eq_rows.append(row)
    b_eq_rows.append(L[t] - PV[t])

# SOC 演化: S_t - S_{t-1} - η c_t Δt + d_t Δt/η = 0
for t in range(N):
    row = np.zeros(nvar)
    row[si(t)] = 1.0
    row[ci(t)] = -ETA * DT
    row[di(t)] = DT / ETA
    A_eq_rows.append(row)
    if t == 0:
        b_eq_rows.append(S0)
    else:
        row[si(t - 1)] = -1.0
        b_eq_rows.append(0.0)

# 周期平衡: S_{N-1} = S0
row = np.zeros(nvar)
row[si(N - 1)] = 1.0
A_eq_rows.append(row)
b_eq_rows.append(S0)

A_eq = np.vstack(A_eq_rows)
b_eq = np.array(b_eq_rows)

# ---- 不等式约束 ----
A_ub_rows, b_ub_rows = [], []

# 电量安全: S_t <= 10800 且 -S_t <= -1200
for t in range(N):
    row = np.zeros(nvar); row[si(t)] = 1.0
    A_ub_rows.append(row); b_ub_rows.append(S_MAX)
    row = np.zeros(nvar); row[si(t)] = -1.0
    A_ub_rows.append(row); b_ub_rows.append(-S_MIN)

# 功率上限: c_t <= 5000, d_t <= 5000
for t in range(N):
    row = np.zeros(nvar); row[ci(t)] = 1.0
    A_ub_rows.append(row); b_ub_rows.append(P_LIM)
    row = np.zeros(nvar); row[di(t)] = 1.0
    A_ub_rows.append(row); b_ub_rows.append(P_LIM)

A_ub = np.vstack(A_ub_rows)
b_ub = np.array(b_ub_rows)

# ---- 变量界: g,c,d,zeta >= 0；S 无下界(由安全区间约束) ----
bounds = ([(0, None)] * n_g + [(0, None)] * n_c + [(0, None)] * n_d
          + [(None, None)] * n_s + [(0, None)] * n_z)

# ---------- 求解 ----------
res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
              bounds=bounds, method="highs")
if not res.success:
    raise RuntimeError(f"LP 求解失败: {res.message}")

x = res.x
g = x[0:n_g]
ch = x[n_g:n_g + n_c]
dis = x[n_g + n_c:n_g + n_c + n_d]
S = x[n_g + n_c + n_d:n_g + n_c + n_d + n_s]
zeta = x[n_g + n_c + n_d + n_s:]
cost = float(res.fun)
total_purchase_kwh = float(g.sum() * DT)
curtail_kwh = float(zeta.sum() * DT)

# ---------- 表 1 ----------
def seg_idx(h, m):
    return h * 6 + m // 10 + 1

spec_segments = [
    ("10:00-10:10", 10, 0), ("12:00-12:10", 12, 0), ("14:00-14:10", 14, 0),
    ("16:00-16:10", 16, 0), ("18:00-18:10", 18, 0), ("20:00-20:10", 20, 0),
]
table1 = [(label, float(g[seg_idx(h, m) - 1] * DT)) for label, h, m in spec_segments]

# ---------- 表 2 ----------
seg_groups = [
    ("0:00-4:00", 0, 24), ("4:00-8:00", 24, 48), ("8:00-12:00", 48, 72),
    ("12:00-16:00", 72, 96), ("16:00-20:00", 96, 120), ("20:00-24:00", 120, 144),
]
table2 = [(lbl, float(ch[a:b].sum() * DT), float(dis[a:b].sum() * DT))
          for lbl, a, b in seg_groups]

# ---------- 验证功率平衡与供电充足 ----------
supply = g + PV + dis      # 供电侧
demand = L + ch + zeta     # 需求侧
balance_err = float(np.abs(supply - demand).max())
shortfall = float((supply - L).min())   # 供电 - 负载，应 >= 0

summary = {
    "决策变量总数": nvar,
    "全天购电量_kWh": round(total_purchase_kwh, 4),
    "全天购电费_元": round(cost, 4),
    "弃光电量_kWh": round(curtail_kwh, 4),
    "0点储电量_kWh": round(float(S0), 4),
    "24点储电量_kWh": round(float(S[-1]), 4),
    "储能SOC_min": round(float(S.min()), 4),
    "储能SOC_max": round(float(S.max()), 4),
    "充电量合计_kWh": round(float(ch.sum() * DT), 4),
    "放电量合计_kWh": round(float(dis.sum() * DT), 4),
    "功率平衡最大误差_kW": round(balance_err, 8),
    "供电减负载最小值_kW": round(shortfall, 4),
    "表1": table1,
    "表2": table2,
}

print("=" * 64)
print("问题 1 求解结果（含弃光变量）")
print("=" * 64)
print(f"决策变量总数 : {nvar}  (g/c/d/S/zeta 各 {N} 个)")
print(f"全天购电量   : {summary['全天购电量_kWh']} kWh")
print(f"全天购电费   : {summary['全天购电费_元']} 元")
print(f"弃光电量     : {summary['弃光电量_kWh']} kWh   <- 应接近 0")
print(f"0:00 / 24:00 : {summary['0点储电量_kWh']} / {summary['24点储电量_kWh']} kWh")
print(f"SOC 区间     : [{summary['储能SOC_min']}, {summary['储能SOC_max']}] kWh")
print(f"功率平衡误差 : {summary['功率平衡最大误差_kW']} kW")
print(f"供电-负载最小: {summary['供电减负载最小值_kW']} kW (>=0 即满足约束)")
print()
print("表 1  指定时段购电量 (kWh)")
print("  " + " | ".join(f"{lbl}: {v:.2f}" for lbl, v in table1))
print()
print("表 2  储能分时段充放电量 (kWh)")
for lbl, c_kwh, d_kwh in table2:
    print(f"  {lbl}: 充电 {c_kwh:.2f}, 放电 {d_kwh:.2f}")

with open(OUT_DIR / "q1_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

np.savez(OUT_DIR / "q1_solution.npz", g=g, ch=ch, dis=dis, S=S, zeta=zeta,
         p=p, L=L, PV=PV, times=np.array(times, dtype=object),
         cost=cost, total_purchase_kwh=total_purchase_kwh, curtail_kwh=curtail_kwh)

print(f"\n结果已保存: {OUT_DIR / 'q1_summary.json'}")
