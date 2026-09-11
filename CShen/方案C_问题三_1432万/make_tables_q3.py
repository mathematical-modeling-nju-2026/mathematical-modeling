"""生成论文中表1/表2/表3（指定日期 2025.3.20 / 6.21 / 9.23 / 12.21）。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DT = 1 / 6

d = np.load(HERE / "_q3_result.npz", allow_pickle=True)
dates = [str(x) for x in d["dates"]]
g_plan = d["g_plan"]; g_final = d["g_final"]
c = d["c"]; dis = d["d"]; e = d["e"]
E_start = d["E_start"]; E_end = d["E_end"]; price = d["price"]

TARGET = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]


def idx_of(s):
    return dates.index(s)


def _lbl(t):
    m = t * 10
    return "24:00" if m == 1440 else f"{m // 60}:{m % 60:02d}"


def merge(ei, tol=1e-6):
    out, t = [], 0
    while t < 144:
        if ei[t] > tol:
            t0, q = t, 0.0
            while t < 144 and ei[t] > tol:
                q += ei[t]; t += 1
            out.append((_lbl(t0), _lbl(t), q))
        else:
            t += 1
    return out


print("# 表1 微网在指定日期的计划购电量（每 4 小时块汇总，单位 kWh）")
print("| 日期 | " + " | ".join(f"{h}h块" for h in range(0, 24, 4)) + " | 全天 | 购电费(元) |")
print("|---|" + "---|" * 8)
for s in TARGET:
    i = idx_of(s)
    gp = g_plan[i]
    blocks = [gp[b*24:(b+1)*24].sum() for b in range(6)]
    print(f"| {s} | " + " | ".join(f"{v:.1f}" for v in blocks) +
          f" | {gp.sum():.1f} | {price@gp:.2f} |")

print("\n# 表2 微网在指定日期的储能充放电量（单位 kWh）")
print("| 日期 | 时段 | 充电量 | 放电量 | 时段末储电量 |")
print("|---|---|---|---|---|")
for s in TARGET:
    i = idx_of(s)
    Etraj = np.concatenate([[E_start[i]], E_start[i] + np.cumsum(0.9*c[i]-dis[i]/0.9)])
    for b in range(6):
        a0, b0 = b*24, (b+1)*24
        print(f"| {s} | {b*4}:00-{b*4+4}:00 | {c[i,a0:b0].sum():.1f} | "
              f"{dis[i,a0:b0].sum():.1f} | {Etraj[b0]:.1f} |")
    print(f"| {s} | 0:00 | — | — | {E_start[i]:.1f} |")

print("\n# 表3 微网在指定日期的紧急购电量")
print("| 日期 | 紧急购电时间段 | 购电量(kWh) |")
print("|---|---|---|")
for s in TARGET:
    i = idx_of(s)
    ivs = merge(e[i])
    if not ivs:
        print(f"| {s} | — | 0 |"); continue
    for j, (a, b, q) in enumerate(ivs):
        print(f"| {s if j == 0 else ''} | {a}-{b} | {q:.1f} |")

print("\n# 费用汇总（指定日期）")
print("| 日期 | 计划购电费 | 调整费 | 紧急购电费 | 当日合计 |")
print("|---|---|---|---|---|")
for s in TARGET:
    i = idx_of(s)
    gp, ga = g_plan[i], g_final[i]
    u = np.maximum(ga - gp, 0); v = np.maximum(gp - ga, 0)
    pc = float(price @ gp)
    dc = float(1.5 * (price @ u) - 0.5 * (price @ v))
    ec = float(5.0 * (price @ e[i]))
    print(f"| {s} | {pc:.2f} | {dc:.2f} | {ec:.2f} | {pc+dc+ec:.2f} |")
