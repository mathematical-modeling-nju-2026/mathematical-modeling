"""问题1 主流程：读数据 -> 建LP -> 求解 -> 校验 -> MILP对照 -> 导出结果。"""

import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from q1_model import (load_attachment1, solve_lp, solve_milp, unpack, verify,
                      baseline_no_storage, marginal_price, CAP, E_INIT, T, DT)

ROOT = Path(__file__).resolve().parents[2]
ATT1 = ROOT / "data" / "附件" / "附件1.xlsx"
OUT = Path(__file__).resolve().parents[1] / "results"

# 附件5 未提供，按题目表1/表2 的时间段自行定义
TABLE1_SLOTS = ["10:00-10:10", "12:00-12:10", "14:00-14:10",
                "16:00-16:10", "18:00-18:10", "20:00-20:10"]
TABLE2_BLOCKS = ["0:00-4:00", "4:00-8:00", "8:00-12:00",
                 "12:00-16:00", "16:00-20:00", "20:00-24:00"]


def slot_index(start_hhmm):
    """'10:00-10:10' -> 该段在 1..144 中的序号。"""
    h, m = map(int, start_hhmm.split("-")[0].split(":"))
    return h * 6 + m // 10 + 1


def block_index(block):
    """'8:00-12:00' -> (起段序号, 止段序号)，含两端。"""
    a, b = block.split("-")
    ha, ma = map(int, a.split(":"))
    hb, mb = map(int, b.split(":"))
    t0 = (ha * 60 + ma) // 10 + 1
    t1 = (hb * 60 + mb) // 10
    return t0, t1


def main():
    labels, price, load, pv = load_attachment1(ATT1)
    print("=" * 68)
    print("输入数据概览（附件1）")
    print("=" * 68)
    print(f"  时段数        : {T}  (每段 {DT:.4f} h)")
    print(f"  电价 元/kWh   : {price.min():.4f} ~ {price.max():.4f}  均值 {price.mean():.4f}")
    print(f"  负载 kWh/段   : {load.min():.2f} ~ {load.max():.2f}  全天 {load.sum():.2f} kWh")
    print(f"  光伏 kWh/段   : {pv.min():.2f} ~ {pv.max():.2f}  全天 {pv.sum():.2f} kWh")

    # ---- 求解 ----
    obj_lp, x_lp = solve_lp(price, load, pv)
    sol = unpack(x_lp)
    print("\n" + "=" * 68)
    print("求解结果")
    print("=" * 68)
    print(f"  LP  全天购电费 : {obj_lp:,.2f} 元")

    obj_milp, x_milp = solve_milp(price, load, pv)
    print(f"  MILP全天购电费 : {obj_milp:,.2f} 元   (含充放电互斥约束)")

    base_cost, g_base = baseline_no_storage(price, load, pv)
    print(f"  无储能基线费用 : {base_cost:,.2f} 元")
    save = base_cost - obj_lp
    print(f"  节省费用       : {save:,.2f} 元  ({save / base_cost * 100:.2f}%)")

    # ---- 校验 ----
    print("\n" + "=" * 68)
    print("解的性质校验")
    print("=" * 68)
    for name, ok, detail in verify(sol, price, load, pv):
        print(f"  [{'✓' if ok else '✗'}] {name:<28} {detail}")

    gap = abs(obj_lp - obj_milp)
    print(f"\n  LP 与 MILP 目标值差 : {gap:.6f} 元  "
          f"-> {'二者等价，LP 松弛是紧的' if gap < 1e-4 else '存在差异，需检查'}")

    # ---- 分时段电量来源分解 ----
    print("\n" + "=" * 68)
    print("全天电量构成")
    print("=" * 68)
    print(f"  外网购电      : {sol['g'].sum():>12,.2f} kWh")
    print(f"  光伏发电      : {pv.sum():>12,.2f} kWh")
    print(f"  电池放电      : {sol['d'].sum():>12,.2f} kWh")
    print(f"  小区负载      : {load.sum():>12,.2f} kWh")
    print(f"  电池充电      : {sol['c'].sum():>12,.2f} kWh")
    print(f"  弃光          : {sol['w'].sum():>12,.2f} kWh")
    print(f"  往返损失      : {ETA_LOSS(sol):>12,.2f} kWh")
    print(f"  谷段/峰段购电 : 参见图2")

    # ---- 系统边际电价（能量平衡约束的对偶变量）----
    print("\n" + "=" * 68)
    print("系统边际电价 λ_t（能量平衡约束的对偶变量，元/kWh）")
    print("=" * 68)
    lam = marginal_price(price, load, pv)
    srt = np.argsort(lam)
    print("  λ 最低的 6 个时段（充电首选）:")
    for i in srt[:6]:
        print(f"    {labels[i]}   λ={lam[i]:.4f}   电价={price[i]:.4f}   光伏={pv[i]:7.1f} kWh")
    print("  λ 最高的 6 个时段（放电首选）:")
    for i in srt[-6:][::-1]:
        print(f"    {labels[i]}   λ={lam[i]:.4f}   电价={price[i]:.4f}   光伏={pv[i]:7.1f} kWh")
    np.savez(OUT / "duals.npz", lam=lam)

    # ---- 表1 ----
    print("\n" + "=" * 68)
    print("表1  微网在指定时间段的购电量及全天的购电量和购电费")
    print("=" * 68)
    print(f"  {'时间段':<16}{'购电量(kWh)':>14}{'电价(元/kWh)':>14}")
    for s in TABLE1_SLOTS:
        t = slot_index(s) - 1
        print(f"  {s:<16}{sol['g'][t]:>14.2f}{price[t]:>14.4f}")
    print(f"  {'-' * 44}")
    print(f"  {'全天购电量':<16}{sol['g'].sum():>14.2f}")
    print(f"  {'全天购电费':<16}{obj_lp:>14.2f} 元")

    # ---- 表2 ----
    print("\n" + "=" * 68)
    print("表2  储能设备在指定时间段的充放电量及 0:00 和 24:00 的储电量")
    print("=" * 68)
    print(f"  {'时间段':<16}{'充电量(kWh)':>14}{'放电量(kWh)':>14}")
    for b in TABLE2_BLOCKS:
        t0, t1 = block_index(b)
        c_sum = sol["c"][t0 - 1:t1].sum()
        d_sum = sol["d"][t0 - 1:t1].sum()
        print(f"  {b:<16}{c_sum:>14.2f}{d_sum:>14.2f}")
    print(f"  {'-' * 44}")
    print(f"  {'0:00 储电量':<16}{E_INIT:>14.2f}")
    print(f"  {'24:00 储电量':<16}{sol['E'][-1]:>14.2f}")

    # ---- 导出 ----
    export_xlsx(labels, sol, obj_lp, OUT / "result1.xlsx")
    export_detail_csv(labels, price, load, pv, sol, OUT / "schedule_detail.csv")
    np.savez(OUT / "solution.npz", labels=np.array(labels), price=price, load=load,
             pv=pv, g=sol["g"], c=sol["c"], d=sol["d"], w=sol["w"], E=sol["E"],
             obj_lp=obj_lp, obj_milp=obj_milp, base_cost=base_cost)
    print(f"\n已导出: {OUT / 'result1.xlsx'}")
    print(f"已导出: {OUT / 'schedule_detail.csv'}")
    print(f"已导出: {OUT / 'solution.npz'}")


def ETA_LOSS(sol):
    """往返效率造成的电量损失。"""
    from q1_model import ETA
    return sol["c"].sum() - (sol["E"][-1] - E_INIT) - sol["d"].sum()


def export_xlsx(labels, sol, obj, path):
    """按附件5 result1.xlsx 模板导出（表头复用模板 + 环形映射）。

    模板标签为左端点且首格 0:10-0:20、末格 0:00+1-0:10+1，与内部时段
    相差一格；故模板第 i 行 ← 内部时段 (i+1) % 144。
    依据官方 CUMCM2026Problems/C题/问题一/make_result1.py。
    """
    import openpyxl
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                          / "common" / "efficiency"))
    from template_layout import TPL1, block_labels, template_labels
    tpl_labels = template_labels(TPL1, "计划购电量")
    blocks6 = block_labels(TPL1, "充放电量")

    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "计划购电量"
    ws.append(["时间段", "购电量"])
    for i, lab in enumerate(tpl_labels):
        ws.append([lab, round(float(sol["g"][(i + 1) % 144]), 6)])
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 16

    ws2 = wb.create_sheet("充放电量")
    ws2.append(["时间段", "充电量", "放电量", "时刻", "储电量"])
    for b in range(6):
        ws2.append([blocks6[b],
                    round(float(sol["c"][b * 24:(b + 1) * 24].sum()), 6),
                    round(float(sol["d"][b * 24:(b + 1) * 24].sum()), 6),
                    "0:00" if b == 0 else ("24:00" if b == 1 else None),
                    E_INIT if b == 0 else
                    (round(float(sol["E"][-1]), 6) if b == 1 else None)])
    for col, wd in zip("ABCDE", (16, 16, 16, 10, 16)):
        ws2.column_dimensions[col].width = wd

    wb.save(path)


def export_detail_csv(labels, price, load, pv, sol, path):
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["时间", "电价(元/kWh)", "负载(kWh)", "光伏(kWh)",
                    "购电量(kWh)", "充电量(kWh)", "放电量(kWh)",
                    "弃光量(kWh)", "储电量(kWh)"])
        for i, lab in enumerate(labels):
            w.writerow([lab, f"{price[i]:.4f}", f"{load[i]:.4f}", f"{pv[i]:.4f}",
                        f"{sol['g'][i]:.4f}", f"{sol['c'][i]:.4f}",
                        f"{sol['d'][i]:.4f}", f"{sol['w'][i]:.4f}",
                        f"{sol['E'][i]:.4f}"])


if __name__ == "__main__":
    main()
