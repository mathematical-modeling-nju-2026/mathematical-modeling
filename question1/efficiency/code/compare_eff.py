"""对比问题1 两种效率定义的结果差异。"""
import json
import pathlib

import numpy as np
import pandas as pd

BASE = pathlib.Path(r"d:\数学建模大赛\mathematical-modeling\question1\efficiency")
DEFS = [("def1_side90", "定义一：充/放各 90%（往返 0.81）"),
        ("def2_roundtrip90", "定义二：放电/充电 = 90%（往返 0.90）")]

out = []


def add(s=""):
    out.append(s)


# ---------- 汇总对照 ----------
add("=" * 88)
add("问题1  两种「90% 效率」定义的对照")
add("=" * 88)

rows = []
summ = {}
for key, name in DEFS:
    j = json.loads((BASE / key / "results" / "summary.json").read_text(encoding="utf-8"))
    summ[key] = j
    rows.append(dict(
        定义=name,
        η_c=round(j["eta_charge"], 6),
        η_d=round(j["eta_discharge"], 6),
        往返=round(j["eta_roundtrip"], 6),
        购电费=round(j["obj_lp_yuan"], 2),
        购电量=round(j["g_kwh"], 2),
        充电=round(j["c_kwh"], 2),
        放电=round(j["d_kwh"], 2),
        损失=round(j["roundtrip_loss_kwh"], 2),
    ))
df = pd.DataFrame(rows)
add(df.to_string(index=False))
add()

a, b = summ["def1_side90"], summ["def2_roundtrip90"]
add("差异（定义二 − 定义一）")
add(f"  全天购电费    : {b['obj_lp_yuan'] - a['obj_lp_yuan']:>+12,.2f} 元  "
    f"({(b['obj_lp_yuan'] / a['obj_lp_yuan'] - 1) * 100:+.2f}%)")
add(f"  全天购电量    : {b['g_kwh'] - a['g_kwh']:>+12,.2f} kWh")
add(f"  电池充电量    : {b['c_kwh'] - a['c_kwh']:>+12,.2f} kWh")
add(f"  电池放电量    : {b['d_kwh'] - a['d_kwh']:>+12,.2f} kWh")
add(f"  往返损失      : {b['roundtrip_loss_kwh'] - a['roundtrip_loss_kwh']:>+12,.2f} kWh")
add(f"  节省费用      : {b['saving_yuan'] - a['saving_yuan']:>+12,.2f} 元")
add(f"  节省比例      : {a['saving_percent']:.2f}%  →  {b['saving_percent']:.2f}%")
add()

# ---------- 收益分解 ----------
add("=" * 88)
add("收益来源分解对照")
add("=" * 88)
add(f"  {'项目':<16}{'定义一(元)':>16}{'定义二(元)':>16}{'差异':>14}")
for k, lbl in [("absorb_gain_yuan", "光伏余电消纳"),
               ("arbitrage_gain_yuan", "峰谷价差套利"),
               ("saving_yuan", "合计节省")]:
    add(f"  {lbl:<16}{a[k]:>16,.2f}{b[k]:>16,.2f}{b[k] - a[k]:>+14,.2f}")
add()
add("  两定义的①光伏余电消纳完全相同（基线一致、余电量一致）——")
add("  差异全部来自②套利：往返效率提高 → 套利空间变大。")
add()

# ---------- 逐时段差异 ----------
add("=" * 88)
add("逐时段调度差异（绝对值 > 1 kWh 的时段）")
add("=" * 88)
d1 = pd.read_csv(BASE / "def1_side90" / "results" / "schedule_detail.csv")
d2 = pd.read_csv(BASE / "def2_roundtrip90" / "results" / "schedule_detail.csv")
cols = list(d1.columns)
add(f"  列: {cols}")
diff = (d2[cols[4:]] - d1[cols[4:]]).abs()
mask = diff.max(axis=1) > 1.0
add(f"  有差异的时段数: {int(mask.sum())} / {len(d1)}")
sel = d1.loc[mask, [cols[0]]].copy()
for c in cols[4:7]:
    sel[f"Δ{c}"] = (d2.loc[mask, c] - d1.loc[mask, c]).round(2)
add(sel.to_string(index=False))
add()

# ---------- 表1/表2 ----------
add("=" * 88)
add("题目表1（指定时段购电量）对照")
add("=" * 88)
paper_slots = ["10:00-10:10", "12:00-12:10", "14:00-14:10",
               "16:00-16:10", "18:00-18:10", "20:00-20:10"]
add(f"  {'时段':<14}{'定义一':>12}{'定义二':>12}{'电价':>10}")
for end in ["10:10", "12:10", "14:10", "16:10", "18:10", "20:10"]:
    i = d1.index[d1[cols[0]] == end]
    if len(i) == 0:
        continue
    i = i[0]
    add(f"  {end:<14}{d1.loc[i, '购电量(kWh)']:>12.2f}"
        f"{d2.loc[i, '购电量(kWh)']:>12.2f}{d1.loc[i, '电价(元/kWh)']:>10.4f}")
add()

add("=" * 88)
add("题目表2（充放电量）对照")
add("=" * 88)
blocks = [("0:00-4:00", 0, 24), ("4:00-8:00", 24, 48), ("8:00-12:00", 48, 72),
          ("12:00-16:00", 72, 96), ("16:00-20:00", 96, 120), ("20:00-24:00", 120, 144)]
add(f"  {'时段':<14}{'充(定义一)':>12}{'充(定义二)':>12}"
    f"{'放(定义一)':>12}{'放(定义二)':>12}")
for name, i0, i1 in blocks:
    c1 = d1.loc[i0:i1 - 1, '充电量(kWh)'].sum()
    c2 = d2.loc[i0:i1 - 1, '充电量(kWh)'].sum()
    v1 = d1.loc[i0:i1 - 1, '放电量(kWh)'].sum()
    v2 = d2.loc[i0:i1 - 1, '放电量(kWh)'].sum()
    add(f"  {name:<14}{c1:>12.2f}{c2:>12.2f}{v1:>12.2f}{v2:>12.2f}")

txt = "\n".join(out)
(BASE / "comparison.txt").write_text(txt, encoding="utf-8")
print(txt)
