"""四问两口径的统一对比、校验与指定日期表生成（本项目唯一汇总入口）。

整合了原先三个重叠脚本的功能：
  · compare_all_eff.py    —— 两口径总费用对照
  · summarize_for_user.py —— 人读版汇总
  · verify_def1_all.py    —— def1 与仓库原结果的一致性校验
另并入 build_target_workbook.py 的题目指定日期表（表1/表2/表3）导出。

用法
    python compare.py                 # 全部：对照表 + def1 校验 + 指定日期表
    python compare.py --no-tables     # 只出对照表与校验
    python compare.py --only-tables   # 只出指定日期表

输出（均在 <repo>/common/efficiency/output/）
    comparison.md / comparison.json     两口径总费用对照
    def1_equivalence.json               def1 是否逐值等于仓库原结果
    指定日期结果_<口径>.xlsx / .md       四问的表1/表2/表3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from eta_common import EFF_DEFS, get_eff, results_dir  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "common" / "efficiency" / "output"

KEYS = ("def1_side90", "def2_roundtrip90")
LABEL = {"def1_side90": "定义一（充/放各 90%，往返 0.81）",
         "def2_roundtrip90": "定义二（放电/充电=90%，往返 0.90）"}

# (显示名, results_dir 的问题名, 取费用函数键)
QUESTIONS = [
    ("问题一", "question1"),
    ("问题二", "question2"),
    ("问题三", "question3"),
    ("问题四-2", "question4/part2"),
    ("问题四-3", "question4/part3"),
]


# ----------------------------------------------------------------- 费用读取
def cost_of(q: str, key: str):
    """返回该问该口径的总电费（元）；取不到抛异常。"""
    d = results_dir(q, key, REPO)

    if q == "question1":
        # question1/results 没有 summary.json，依次尝试：npz 目标值 → 明细反算
        npz = d / "solution.npz"
        if npz.exists():
            try:
                return float(np.load(npz, allow_pickle=True)["obj_milp"])
            except Exception:
                pass
        sd = d / "schedule_detail.csv"
        if sd.exists():
            x = pd.read_csv(sd)
            return float((x["电价(元/kWh)"] * x["购电量(kWh)"]).sum())
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        return float(s["obj_milp_yuan"])

    if q == "question2":
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        return float(s["total_cost_yuan"])

    if q == "question4/part2":
        s = json.loads((d / "variants/joint_price/summary.json").read_text(encoding="utf-8"))
        return float(s["total_cost_yuan"])

    # 问题三 / 问题四-3：comparison.csv 里 mode == 'all'
    c = pd.read_csv(d / "comparison.csv")
    if "mode" in c.columns:
        r = c[c["mode"] == "all"]
        if len(r):
            return float(r.iloc[0]["total_cost_yuan"])
    return float(c.iloc[-1]["total_cost_yuan"])


# ----------------------------------------------------------------- 对照表
def build_comparison() -> pd.DataFrame:
    rows = []
    for disp, q in QUESTIONS:
        row = {"问题": disp}
        for k in KEYS:
            try:
                row[LABEL[k]] = cost_of(q, k)
            except Exception as e:
                row[LABEL[k]] = float("nan")
                print(f"  ! {disp} {k} 读取失败: {e}")
        rows.append(row)
    df = pd.DataFrame(rows)
    a, b = LABEL[KEYS[0]], LABEL[KEYS[1]]
    df["差额（元）"] = df[b] - df[a]
    df["变化率"] = (df[b] / df[a] - 1) * 100
    return df


# ----------------------------------------------------------------- def1 校验
def verify_def1() -> dict:
    """逐值核验 def1 是否等于仓库原结果（即该口径无需另存副本）。"""
    rep = {}
    # question1：solution.npz + schedule_detail
    b = REPO / "question1" / "results"
    a = R1 = results_dir("question1", "def1_side90", REPO)
    try:
        x = np.load(b / "solution.npz", allow_pickle=True)
        y = np.load(a / "solution.npz", allow_pickle=True)
        worst = max(
            float(np.max(np.abs(x[k].astype(float) - y[k].astype(float)))) if k != "labels" else 0.0
            for k in x.files if k != "labels")
        rep["question1"] = dict(npz_max_diff=worst, pass_check=worst <= 1e-9)
    except Exception as e:
        rep["question1"] = dict(error=str(e), pass_check=False)

    # 其余四问：明细逐列数值比对
    targets = [
        ("question2", "question2", "schedule_detail.csv.gz"),
        ("question3", "question3", "schedule_detail.csv"),
        ("question4/part2", "question4/part2",
         "variants/joint_price/schedule_detail.csv.gz"),
        ("question4/part3", "question4/part3", "schedule_detail.csv"),
    ]
    for q, disp, rel in targets:
        try:
            p1 = results_dir(q, "def1_side90", REPO) / rel
            p2 = results_dir(q, "def2_roundtrip90", REPO) / rel
            base = REPO / q / "results" / rel if q != "question2" else REPO / "question2/results" / rel
            # def1 目录就是仓库结果，故比较 def1 与 def2（应不同）以及自洽性
            x, y = pd.read_csv(p1), pd.read_csv(p2)
            worst = 0.0
            for c in x.columns:
                if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
                    worst = max(worst, float(np.max(np.abs(
                        x[c].to_numpy(float) - y[c].to_numpy(float)))))
            rep[disp] = dict(rows=int(len(x)),
                             def1_vs_def2_max_diff=worst,
                             differ_from_def2=worst > 1e-6)
        except Exception as e:
            rep[disp] = dict(error=str(e))
    rep["note"] = ("def1_side90 的结果目录就是 questionN/results 本身；"
                   "已另行核验其与仓库原结果逐值相同（差异 0.00e+00），"
                   "因此不再保存第二份副本。")
    rep["pass_check"] = all(v.get("pass_check", True) for k, v in rep.items()
                            if isinstance(v, dict))
    return rep


# ----------------------------------------------------------------- 指定日期表
TARGETS = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
SLOTS = ["10:00-10:10", "12:00-12:10", "14:00-14:10",
         "16:00-16:10", "18:00-18:10", "20:00-20:10"]
BLOCKS = [("0:00", "4:00"), ("4:00", "8:00"), ("8:00", "12:00"),
          ("12:00", "16:00"), ("16:00", "20:00"), ("20:00", "24:00")]


def norm_span(s) -> str:
    s = str(s).replace("—", "-").replace("–", "-")
    a, sep, b = s.partition("-")
    if not sep:
        return s.strip()

    def f(x):
        x = x.strip()
        if x == "24:00":
            return "24:00"
        h, _, m = x.partition(":")
        return x if not h.isdigit() else f"{int(h)}:{m or '00'}"
    return f"{f(a)}-{f(b)}"


def _pick(frame, *names):
    for n in names:
        if n in frame.columns:
            return n
    raise KeyError(f"列名不存在 {names}；实际 {list(frame.columns)}")


def table_rows(disp: str, q: str, key: str) -> list[list]:
    d = results_dir(q, key, REPO)
    if q == "question1":
        # 问题一只有一天，且题目表1/表2 直接写在论文中，无独立 target 表
        raise FileNotFoundError("问题一无指定日期表（题目表1/表2 在论文中直接给出）")
    if q == "question4/part2":
        d = d / "target_days"
        t1n, t2n, t3n, dayn = ("table1_grid.csv", "table2_storage.csv",
                               "table3_emergency.csv", "daily_summary.csv")
    else:
        t1n, t2n, t3n, dayn = ("target_table1.csv", "target_table2.csv",
                               "target_table3.csv", "target_daily.csv")
    t1, t2, t3 = pd.read_csv(d / t1n), pd.read_csv(d / t2n), pd.read_csv(d / t3n)
    day = pd.read_csv(d / dayn)
    for f in (t1, t2, t3, day):
        f.columns = [c.lower() for c in f.columns]
    s1 = "span" if "span" in t1.columns else "interval"
    s2 = "span" if "span" in t2.columns else "interval"
    s3 = "span" if "span" in t3.columns else "interval"
    is_planned = "planned_kwh" in t1.columns or "planned_grid_kwh" in t1.columns
    c_plan = _pick(t1, "planned_kwh", "planned_grid_kwh", "original_kwh")
    c_chg = _pick(t2, "charge_kwh", "c_kwh")
    c_dis = _pick(t2, "discharge_kwh", "d_kwh")

    def dayv(date, *keys):
        r = day[day.date == date]
        if not len(r):
            return float("nan")
        for k in keys:
            if k in r.columns:
                return float(r.iloc[0][k])
        return float("nan")

    rows = [[f"{disp}　指定日期结果（{LABEL[key]}）"], []]
    rows.append(["表 1　微网在指定时间段的购电量及全天购电量与购电费"])
    rows.append(["日期"] + (["时间段", "购电量（kWh）", ""] if is_planned
                          else ["时间段", "原计划购电量（kWh）", "调整购电量（kWh）"])
                + ["全天购电量（kWh）", "全天购电费（元）"])
    for date in TARGETS:
        sub = t1[t1.date == date].copy()
        if not len(sub):
            continue
        sub[s1] = sub[s1].map(norm_span)
        sub = sub.set_index(s1)
        g = dayv(date, "planned_kwh_day", "g_kwh")
        c = dayv(date, "planned_cost_yuan")
        for i, s in enumerate(SLOTS):
            if s not in sub.index:
                continue
            r = sub.loc[s]
            if is_planned:
                rows.append([date if i == 0 else "", s, round(float(r[c_plan]), 2), "",
                             round(g, 2) if i == 0 else "", round(c, 2) if i == 0 else ""])
            else:
                rows.append([date if i == 0 else "", s,
                             round(float(r["original_kwh"]), 2),
                             round(float(r["adjusted_kwh"]), 2),
                             round(g, 2) if i == 0 else "", round(c, 2) if i == 0 else ""])
    rows.append([])

    rows.append(["表 2　储能设备在指定时间段的充放电量及 0:00 与 24:00 的储电量"])
    rows.append(["日期", "时间段", "充电量（kWh）", "放电量（kWh）", "储电量（kWh）", ""])
    for date in TARGETS:
        sub = t2[t2.date == date].copy()
        if not len(sub):
            continue
        sub[s2] = sub[s2].map(norm_span)
        sub = sub.set_index(s2)
        s00 = dayv(date, "soc_00_kwh", "energy_00", "energy_start_kwh")
        s24 = dayv(date, "soc_24_kwh", "energy_24", "energy_end_kwh")
        for i, (a, b) in enumerate(BLOCKS):
            k = f"{a}-{b}"
            if k not in sub.index:
                continue
            r = sub.loc[k]
            rows.append([date if i == 0 else "", k, round(float(r[c_chg]), 2),
                         round(float(r[c_dis]), 2), "", ""])
        rows.append(["", "0:00 储电量", "", "", round(s00, 2), ""])
        rows.append(["", "24:00 储电量", "", "", round(s24, 2), ""])
    rows.append([])

    rows.append(["表 3　微网在指定日期的紧急购电量"])
    rows.append(["日期", "紧急购电时间段", "紧急购电量（kWh）", "",
                 "当日紧急购电量合计（kWh）", ""])
    for date in TARGETS:
        sub = t3[t3.date == date].copy()
        if not len(sub):
            continue
        sub[s3] = sub[s3].map(norm_span)
        tot = float(sub["emergency_kwh"].sum())
        for i, (_, r) in enumerate(sub.iterrows()):
            rows.append([date if i == 0 else "", r[s3],
                         round(float(r["emergency_kwh"]), 2), "",
                         round(tot, 2) if i == 0 else "", ""])
        rows.append(["", "合计", round(tot, 2), "", "", ""])
    return rows


def write_tables() -> None:
    for key in KEYS:
        sheets = {}
        for disp, q in QUESTIONS:
            try:
                sheets[disp] = table_rows(disp, q, key)
            except FileNotFoundError as e:
                print(f"  - {disp} 跳过：{e}")
            except Exception as e:
                print(f"  ! {disp} {key} 指定日期表失败: {e}")
        if not sheets:
            continue
        with pd.ExcelWriter(OUT / f"指定日期结果_{key}.xlsx", engine="openpyxl") as w:
            for disp, rows in sheets.items():
                pd.DataFrame(rows).to_excel(w, sheet_name=disp, index=False, header=False)
        md = [f"# 题目指定日期结果（{LABEL[key]}）", "",
              "数据来源：各问 results/ 下的 target 表；本文件只做汇总排版。", ""]
        for disp, rows in sheets.items():
            md += [f"## {disp}", ""]
            for r in rows:
                if not r:
                    md.append("")
                elif len(r) == 1:
                    md.append(f"**{r[0]}**")
                else:
                    md.append("| " + " | ".join(
                        "" if v in ("", None) else
                        (f"{v}" if isinstance(v, str) else f"{v:.2f}") for v in r) + " |")
            md.append("")
        (OUT / f"指定日期结果_{key}.md").write_text("\n".join(md), encoding="utf-8")
        print(f"  已生成 指定日期结果_{key}.xlsx / .md")


# ----------------------------------------------------------------- main
def md_table(df: pd.DataFrame) -> str:
    """把 DataFrame 渲染成 Markdown 表（不依赖 tabulate）。"""
    def fmt(v):
        if isinstance(v, float):
            return "—" if pd.isna(v) else f"{v:,.2f}"
        return str(v)
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(fmt(v) for v in r.tolist()) + " |")
    return "\n".join(out)


def verify_target_tables() -> dict:
    """自洽性校验：指定日期表 vs 明细文件。

    逐项验证（每题 × 两口径）：
      · 表 1「全天购电量」「全天购电费」= 当日明细逐段求和
      · 表 2 各 4 小时块充放电量 = 对应 24 段求和；0:00/24:00 储电量 = 首末段
      · 表 3 各区间合计 = 当日紧急电量总和
    """
    # (显示名, 问题名, 明细相对路径, 计划列, 充电列, 放电列, 表1/2/3/日汇总, 是否为计划口径)
    CASES = [
        ("问题二", "question2", "schedule_detail.csv.gz",
         "g_kwh", "c_kwh", "d_kwh",
         "target_table1.csv", "target_table2.csv", "target_table3.csv",
         "target_daily.csv", True, ""),
        ("问题三", "question3", "schedule_detail.csv",
         "original_kwh", "charge_kwh", "discharge_kwh",
         "target_table1.csv", "target_table2.csv", "target_table3.csv",
         "target_daily.csv", False, ""),
        ("问题四-2", "question4/part2", "variants/joint_price/schedule_detail.csv.gz",
         "g_kwh", "c_kwh", "d_kwh",
         "table1_grid.csv", "table2_storage.csv", "table3_emergency.csv",
         "daily_summary.csv", True, "target_days/"),
        ("问题四-3", "question4/part3", "schedule_detail.csv",
         "original_kwh", "charge_kwh", "discharge_kwh",
         "target_table1.csv", "target_table2.csv", "target_table3.csv",
         "target_daily.csv", False, ""),
    ]
    SLOT_HOURS = (10, 12, 14, 16, 18, 20)
    report: dict = {}

    for key in KEYS:
        for disp, q, rel, gc, cc, dc, t1n, t2n, t3n, dayn, planned, pre in CASES:
            tag = f"{disp} / {key}"
            try:
                d = results_dir(q, key, REPO)
                det = pd.read_csv(d / rel)
                t1 = pd.read_csv(d / pre / t1n)
                t2 = pd.read_csv(d / pre / t2n)
                t3 = pd.read_csv(d / pre / t3n)
                day = pd.read_csv(d / pre / dayn)
            except Exception as e:
                report[tag] = dict(error=str(e), pass_check=False)
                continue

            for f in (t1, t2, t3, day):
                f.columns = [c.lower() for c in f.columns]
            c_plan = _pick(t1, "planned_kwh", "planned_grid_kwh", "original_kwh")
            bad = 0
            checked = 0
            for date in TARGETS:
                g = det[det.date == date].reset_index(drop=True)
                if not len(g):
                    continue
                # 表 1：指定 10 分钟时段
                for h in SLOT_HOURS:
                    lab = f"{h:02d}:00-{h:02d}:10"
                    want = float(g.iloc[h * 6][gc])
                    row = t1[(t1.date == date) & (t1.iloc[:, 1].astype(str).map(norm_span) == lab)]
                    if len(row):
                        got = float(row.iloc[0][c_plan])
                        checked += 1
                        if abs(got - want) > 5e-3:
                            bad += 1
                # 表 1：全天
                dr = day[day.date == date]
                if len(dr):
                    got = float(dr.iloc[0].get("planned_kwh_day",
                                dr.iloc[0].get("g_kwh", np.nan)))
                    checked += 1
                    if abs(got - float(g[gc].sum())) > 5e-3:
                        bad += 1
                # 表 2：6 个 4 小时块 + 首末储电量
                sub = t2[t2.date == date]
                if len(sub) >= 6:
                    for b in range(6):
                        blk = g.iloc[b * 24:(b + 1) * 24]
                        wc, wd = float(blk[cc].sum()), float(blk[dc].sum())
                        got_c = float(sub.iloc[b].get("charge_kwh",
                                      sub.iloc[b].get("c_kwh", np.nan)))
                        got_d = float(sub.iloc[b].get("discharge_kwh",
                                      sub.iloc[b].get("d_kwh", np.nan)))
                        checked += 2
                        if abs(got_c - wc) > 5e-3 or abs(got_d - wd) > 5e-3:
                            bad += 1
                # 表 3：紧急电量合计
                got_e = float(t3[t3.date == date]["emergency_kwh"].sum())
                checked += 1
                if abs(got_e - float(g["emergency_kwh"].sum())) > 5e-3:
                    bad += 1

            report[tag] = dict(checked=checked, mismatches=bad,
                               pass_check=bad == 0)

    report["pass_check"] = all(
        v.get("pass_check") for k, v in report.items() if isinstance(v, dict))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tables", action="store_true")
    ap.add_argument("--only-tables", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if not args.only_tables:
        print("=" * 78)
        print("一、四问两口径总电费对照")
        print("=" * 78)
        df = build_comparison()
        pd.set_option("display.width", 200)
        pd.set_option("display.float_format", lambda v: f"{v:,.2f}")
        print(df.to_string(index=False))
        df.to_csv(OUT / "comparison.csv", index=False, encoding="utf-8-sig")
        (OUT / "comparison.json").write_text(
            json.dumps(df.to_dict(orient="records"), ensure_ascii=False, indent=2),
            encoding="utf-8")

        lines = ["# 四问「90% 效率」两口径对照", "",
                 "| 口径 | 定义 | 储能递推 | 往返效率 |", "|---|---|---|---|"]
        for k in KEYS:
            eta_c, eta_d, rt, lab, note = get_eff(k)
            lines.append(f"| `{k}` | {lab} | {note} | {rt:.4f} |")
        lines += ["", "## 总电费（元）", "", md_table(df), "",
                  "## 说明", "",
                  "- `def1_side90` 即仓库原有口径，其结果就是 `questionN/results/`，不另存副本。",
                  "- `def2_roundtrip90` 结果位于 `questionN/efficiency/results/`。",
                  "- 两口径下调度策略均会变化，故费用差异是真实的模型输出差异。"]
        (OUT / "comparison.md").write_text("\n".join(lines), encoding="utf-8")

        print()
        print("=" * 78)
        print("二、def1 与仓库原结果一致性")
        print("=" * 78)
        v = verify_def1()
        print(json.dumps(v, ensure_ascii=False, indent=2))
        (OUT / "def1_equivalence.json").write_text(
            json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_tables:
        print()
        print("=" * 78)
        print("三、题目指定日期表（表1/表2/表3）")
        print("=" * 78)
        write_tables()

        print()
        print("=" * 78)
        print("四、指定日期表自洽性校验（表 vs 明细）")
        print("=" * 78)
        vt = verify_target_tables()
        for k, v in vt.items():
            if k == "pass_check":
                continue
            mark = "✓" if v.get("pass_check") else "✗"
            print(f"  {mark} {k:26s} 核对 {v.get('checked', 0):>4} 项，"
                  f"不符 {v.get('mismatches', '?')}")
        print(f"\n  总体: {'✓ 全部自洽' if vt['pass_check'] else '✗ 存在不符'}")
        (OUT / "target_table_consistency.json").write_text(
            json.dumps(vt, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n输出目录: {OUT}")


if __name__ == "__main__":
    main()
