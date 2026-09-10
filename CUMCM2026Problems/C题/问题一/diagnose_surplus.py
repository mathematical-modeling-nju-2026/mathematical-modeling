"""
诊断问题 1 数据是否存在"光伏过剩无处可去"导致等式无可行解的情况。

功率平衡等式: g_t + PV_t + d_t - c_t = L_t,  g_t >= 0
=> 净吸收 = L_t + c_t - d_t >= PV_t  才能成立（把光伏"吃掉"）
   最大吸收能力 = L_t + c_max - d_min = L_t + 5000 (当 d=0)
   若储能已满(S接近上限)则 c_t 受限甚至为0，吸收能力退化为 L_t

检查：
1. PV_t 是否超过 L_t + 5000（硬无解）
2. PV_t > L_t 的时段（光伏过剩时段，必须靠储能充电吸收）
3. 这些时段储能是否有足够的充电空间
"""

from pathlib import Path
import numpy as np
import pandas as pd

ATTACH_DIR = Path(r"d:\数学建模大赛\CUMCM2026Problems\C题\附件")
df = pd.read_excel(ATTACH_DIR / "附件1.xlsx")
p = df["电价"].to_numpy(float)
L = df["小区负载"].to_numpy(float)
PV = df["光伏发电预测功率"].to_numpy(float)
N = len(p)

P_LIM = 5000.0
S_MAX = 10800.0

print("=" * 60)
print("光伏过剩诊断")
print("=" * 60)
print(f"光伏最大功率      : {PV.max():.2f} kW")
print(f"负载最小功率      : {L.min():.2f} kW")
print(f"PV_max - L_min    : {PV.max() - L.min():.2f} kW  (需 < 充电功率上限 {P_LIM})")
print()

# 1. 是否存在 PV > L + 5000 (即使储能功率满额也无法吸收)
hard = PV > (L + P_LIM)
print(f"[1] PV > L+5000 的时段数: {hard.sum()}  (硬无解判定)")
if hard.sum():
    print("    这些时段:", [i for i in range(N) if hard[i]])
print()

# 2. 光伏过剩时段 (PV > L)，必须靠储能充电吸收
surplus = PV > L
surplus_idx = np.where(surplus)[0]
print(f"[2] 光伏 > 负载 的时段数: {surplus.sum()}")
print(f"    净过剩功率总和(需储能吸收): {float((PV - L).clip(min=0).sum()) * (1/6):.2f} kWh")
print(f"    储能可用充电空间(满-空): {S_MAX - 1200:.2f} kWh")
print()

# 3. 每个光伏过剩时段需要的吸收功率 = PV - L
exc = (PV - L).clip(min=0)
print(f"[3] 过剩功率最大: {exc.max():.2f} kW, 平均: {exc[surplus].mean():.2f} kW")
print(f"    过剩功率超过 5000 的时段数: {(exc > P_LIM).sum()}")
print()

# 4. 直观：过剩时段分布（小时）
surplus_hours = sorted(set((i + 1) // 6 for i in surplus_idx))
print(f"[4] 光伏过剩出现的小时: {surplus_hours}  (早7点~下午, 对应白天)")
