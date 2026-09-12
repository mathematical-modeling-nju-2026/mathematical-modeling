"""问题1 主流程（参数化效率版）：读数据 -> 建 LP -> 求解 -> 校验 -> MILP 对照 -> 导出。

与 question1/code/run_q1.py 的差异
    - 支持两种「90% 效率」口径，由 --eff 选择：
        def1_side90        充/放效率各 90%（往返 0.81）—— 仓库原口径
        def2_roundtrip90   放电量/充电量 = 90%（往返 0.90）—— 国标口径，对称拆分
    - 结果分别写入 efficiency/<口径>/results/，不覆盖仓库原有结果
    - 收益分解改为**可复现的严格恒等式**（原绘图脚本中的分解数为硬编码）

收益分解恒等式（对两种效率口径均成立）
    Σ_t p_t·max(L_t - V_t, 0)  -  Σ_t p_t·g_t
      = Σ_t p_t·max(V_t - L_t, 0)            （弃光消除 = 光伏余电被利用的价值）
      + ( Σ_t p_t·d_t - Σ_t p_t·c_t )        （净套利 = 放电收入 - 充电支出）
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent          # .../question1/efficiency/code
ROOT = HERE.parents[2]                          # .../mathematical-modeling
EFF_ROOT = HERE.parent                          # .../question1/efficiency
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "question1" / "code"))

import q1_model_eff as M                        # noqa: E402

ATT1 = ROOT / "data" / "附件" / "附件1.xlsx"
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


def decompose(sol, price, load, pv, base_cost, obj):
    """严格恒等式收益分解（可复现，无硬编码）。"""
    absorb = float(price @ np.maximum(pv - load, 0.0))      # 弃光消除
    arbitrage = float(price @ sol["d"] - price @ sol["c"])  # 净套利
    total = base_cost - obj
    return dict(absorb=absorb, arbitrage=arbitrage, total=total,
                residual=total - absorb - arbitrage)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eff", default="def1_side90", choices=list(M.EFF_DEFS),
                    help="效率口径：def1_side90（往返0.81）或 def2_roundtrip90（往返0.90）")
    ap.add_argument("--out", default=None, help="输出目录；默认 efficiency/<eff>/results")
    args = ap.parse_args()

    eta_c, eta_d, eta_rt = M.set_efficiency(args.eff)
    out = Path(args.out) if args.out else (EFF_ROOT / args.eff / "results")
    out.mkdir(parents=True, exist_ok=True)

    labels, price, load, pv = M.load_attachment1(ATT1)

    print("=" * 74)
    print(f"问题1  效率口径 = {args.eff}")
    print("=" * 74)
    print(f"  {M.EFF_DESC}")
    print(f"  η_c = {eta_c:.6f}   η_d = {eta_d:.6f}   往返 = {eta_rt:.6f}")
    print(f"  输出目录: {out}")
    print()
    print("  输入数据概览（附件1）")
    print(f"    时段数        : {M.T}  (每段 {M.DT:.4f} h)")
    print(f"    电价 元/kWh   : {price.min():.4f} ~ {price.max():.4f}  均值 {price.mean():.4f}")
    print(f"    负载 kWh/段   : {load.min():.2f} ~ {load.max():.2f}  全天 {load.sum():.2f} kWh")
    print(f"    光伏 kWh/段   : {pv.min():.2f} ~ {pv.max():.2f}  全天 {pv.sum():.2f} kWh")

    # ---------- 求解 ----------
    obj_lp, x_lp = M.solve_lp(price, load, pv)
    sol = M.unpack(x_lp)
    obj_milp, x_milp = M.solve_milp(price, load, pv)
    base_cost, g_base = M.baseline_no_storage(price, load, pv)

    print("\n" + "=" * 74)
    print("求解结果")
    print("=" * 74)
    print(f"  LP   全天购电费 : {obj_lp:,.2f} 元")
    print(f"  MILP 全天购电费 : {obj_milp:,.2f} 元   (含充放电互斥约束)")
    print(f"  无储能基线费用  : {base_cost:,.2f} 元")
    print(f"  节省费用        : {base_cost - obj_lp:,.2f} 元 "
          f"({(base_cost - obj_lp) / base_cost * 100:.2f}%)")

    # ---------- 校验 ----------
    print("\n" + "=" * 74)
    print("解的性质校验")
    print("=" * 74)
    checks = M.verify(sol, price, load, pv)
    for name, ok, detail in checks:
        print(f"  [{'✓' if ok else '✗'}] {name:<28} {detail}")
    all_ok = all(ok for _, ok, _ in checks)

    gap = abs(obj_lp - obj_milp)
    print(f"\n  LP 与 MILP 目标值差 : {gap:.6f} 元  "
          f"-> {'二者等价，LP 松弛是紧的' if gap < 1e-4 else '存在差异，需检查'}")

    # ---------- 电量构成 ----------
    loss = float(sol["c"].sum() - (sol["E"][-1] - M.E_INIT) - sol["d"].sum())
    print("\n" + "=" * 74)
    print("全天电量构成")
    print("=" * 74)
    print(f"  外网购电      : {sol['g'].sum():>12,.2f} kWh")
    print(f"  光伏发电      : {pv.sum():>12,.2f} kWh")
    print(f"  电池放电      : {sol['d'].sum():>12,.2f} kWh")
    print(f"  小区负载      : {load.sum():>12,.2f} kWh")
    print(f"  电池充电      : {sol['c'].sum():>12,.2f} kWh")
    print(f"  弃光          : {sol['w'].sum():>12,.2f} kWh")
    print(f"  往返损失      : {loss:>12,.2f} kWh")

    # ---------- 收益分解（可复现） ----------
    dec = decompose(sol, price, load, pv, base_cost, obj_lp)
    print("\n" + "=" * 74)
    print("收益来源分解（严格恒等式，可复现）")
    print("=" * 74)
    print(f"  ① 光伏余电消纳 : {dec['absorb']:>12,.2f} 元  "
          f"({dec['absorb'] / base_cost * 100:5.2f}% of 基线)")
    print(f"  ② 峰谷价差套利 : {dec['arbitrage']:>12,.2f} 元  "
          f"({dec['arbitrage'] / base_cost * 100:5.2f}% of 基线)")
    print(f"  {'-' * 46}")
    print(f"  合计           : {dec['absorb'] + dec['arbitrage']:>12,.2f} 元")
    print(f"  总节省         : {dec['total']:>12,.2f} 元  "
          f"({dec['total'] / base_cost * 100:5.2f}%)")
    print(f"  恒等式残差     : {dec['residual']:>12,.2e} "
          f"({'✓ 恒等成立' if abs(dec['residual']) < 1e-6 else '✗'})")

    # ---------- 对偶 ----------
    lam = M.marginal_price(price, load, pv)
    np.savez(out / "duals.npz", lam=lam)

    # ---------- 表1 / 表2 ----------
    print("\n" + "=" * 74)
    print("表1  微网在指定时间段的购电量及全天的购电量和购电费")
    print("=" * 74)
    print(f"  {'时间段':<16}{'购电量(kWh)':>14}{'电价(元/kWh)':>14}")
    for s in TABLE1_SLOTS:
        t = slot_index(s) - 1
        print(f"  {s:<16}{sol['g'][t]:>14.2f}{price[t]:>14.4f}")
    print(f"  {'-' * 44}")
    print(f"  {'全天购电量':<16}{sol['g'].sum():>14.2f}")
    print(f"  {'全天购电费':<16}{obj_lp:>14.2f} 元")

    print("\n" + "=" * 74)
    print("表2  储能设备在指定时间段的充放电量及 0:00 和 24:00 的储电量")
    print("=" * 74)
    print(f"  {'时间段':<16}{'充电量(kWh)':>14}{'放电量(kWh)':>14}")
    for b in TABLE2_BLOCKS:
        t0, t1 = block_index(b)
        print(f"  {b:<16}{sol['c'][t0 - 1:t1].sum():>14.2f}"
              f"{sol['d'][t0 - 1:t1].sum():>14.2f}")
    print(f"  {'-' * 44}")
    print(f"  {'0:00 储电量':<16}{M.E_INIT:>14.2f}")
    print(f"  {'24:00 储电量':<16}{sol['E'][-1]:>14.2f}")

    # ---------- 导出 ----------
    export_xlsx(labels, sol, obj_lp, out / "result1.xlsx")
    export_detail_csv(labels, price, load, pv, sol, out / "schedule_detail.csv")
    np.savez(out / "solution.npz", labels=np.array(labels), price=price, load=load,
             pv=pv, g=sol["g"], c=sol["c"], d=sol["d"], w=sol["w"], E=sol["E"],
             obj_lp=obj_lp, obj_milp=obj_milp, base_cost=base_cost)

    summary = dict(
        efficiency_key=args.eff,
        efficiency_description=M.EFF_DESC,
        eta_charge=eta_c, eta_discharge=eta_d, eta_roundtrip=eta_rt,
        obj_lp_yuan=obj_lp, obj_milp_yuan=obj_milp, base_cost_yuan=base_cost,
        saving_yuan=base_cost - obj_lp,
        saving_percent=(base_cost - obj_lp) / base_cost * 100,
        g_kwh=float(sol["g"].sum()), c_kwh=float(sol["c"].sum()),
        d_kwh=float(sol["d"].sum()), w_kwh=float(sol["w"].sum()),
        load_kwh=float(load.sum()), pv_kwh=float(pv.sum()),
        roundtrip_loss_kwh=loss,
        absorb_gain_yuan=dec["absorb"], arbitrage_gain_yuan=dec["arbitrage"],
        decomposition_residual=dec["residual"],
        lp_milp_gap=gap, checks_pass=all_ok,
    )
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已导出: {out / 'result1.xlsx'}")
    print(f"已导出: {out / 'schedule_detail.csv'}")
    print(f"已导出: {out / 'solution.npz'}")
    print(f"已导出: {out / 'summary.json'}")
    return summary


def export_xlsx(labels, sol, obj, path):
    import openpyxl
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "计划购电量"
    ws.append(["时间", "购电量(kWh)"])
    for lab, v in zip(labels, sol["g"]):
        ws.append([lab, round(float(v), 6)])
    ws.append(["全天购电量", round(float(sol["g"].sum()), 6)])
    ws.append(["全天购电费(元)", round(float(obj), 6)])
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 16

    ws2 = wb.create_sheet("充放电量")
    ws2.append(["时间段", "充电量(kWh)", "放电量(kWh)"])
    for b in TABLE2_BLOCKS:
        t0, t1 = block_index(b)
        ws2.append([b, round(float(sol["c"][t0 - 1:t1].sum()), 6),
                    round(float(sol["d"][t0 - 1:t1].sum()), 6)])
    ws2.append(["0:00储电量", M.E_INIT])
    ws2.append(["24:00储电量", round(float(sol["E"][-1]), 6)])
    ws2.column_dimensions["A"].width = 16
    ws2.column_dimensions["B"].width = 16
    ws2.column_dimensions["C"].width = 16

    wb.save(path)


def export_detail_csv(labels, price, load, pv, sol, path):
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
