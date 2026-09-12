"""问题4-2 效率口径补齐：独立校验 + 信息校验 + 发布 + 指定日期表。

不重跑优化，只补齐缺失的交付物：
  · verification.json / information_verification.json / publication_verification.json
  · monthly_comparison.csv
  · result4-2.xlsx（顶层，供交付）
  · target_days/{table1_grid,table2_storage,table3_emergency,daily_summary}.csv
  · 结果说明.md
  · figures/*

关键做法（不修改任何原始文件）：
  1. custom verify_q42.check_schedule：原版把 0.9 写死在 SOC 校验行，
     用 eta_common.load_verify_q42_with_eta 做最小文本替换。
  2. q42_model.check_information 里的 solve_horizon 也必须参数化，
     否则解析算例会按 .81 判分。
  3. report_q42.HERE 指向 <eff>/part2/results，但跳过其
     「必须与 verification.json / information_verification.json 均通过」
     的前置断言——那两份文件由本脚本先生成。

用法
    python backfill_q42_eff.py --eff def1_side90
    python backfill_q42_eff.py --eff def2_roundtrip90
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
Q2_CODE = REPO / "question2" / "code"
P2_CODE = REPO / "question4" / "part2" / "code"
ETA_DIR = REPO / "common" / "efficiency"
for p in (ETA_DIR, Q2_CODE, P2_CODE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eta_common import (apply_to_run1439, eff_metadata as _base_eff_metadata, get_eff,  # noqa: E402
                        load_verify_q42_with_eta, make_solve_horizon,
                        results_dir)


def eff_metadata(key):
    meta = _base_eff_metadata(key)
    if key == "def2_roundtrip90":
        meta["efficiency_label"] = "敏感性定义：放电量/充电量 = 90%（对称拆分的往返效率口径）"
    return meta


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eff", default="def1_side90",
                    choices=["def1_side90", "def2_roundtrip90"])
    args = ap.parse_args()

    eta_c, eta_d, rt, label, note = get_eff(args.eff)
    out = results_dir("question4/part2", args.eff, REPO)
    if not (out / "variants").exists():
        raise SystemExit(f"缺少已运行结果: {out}")

    print("=" * 76)
    print(f"问题4-2 补齐交付物  效率口径 = {args.eff}")
    print("=" * 76)
    print(f"  {label}")
    print(f"  η_c={eta_c:.6f} η_d={eta_d:.6f} 往返={rt:.6f}")
    print(f"  输出目录: {out}", flush=True)

    # ---- 0) 载入并参数化各模块 ----
    # q42_model 在模块级 `from run_experiment import ...`，而 run_experiment
    # 又经 rolling_window.base（即 common/q2_base/run_1439.py）提供 Q2 基线
    # 求解器；check_information 的 constant_price_reduces_to_q2 会用
    # base.solve_horizon 复算「固定电价退化为 Q2」的解析例。若不覆盖
    # run_1439 的 ETA，该例会用 0.9/0.9 求解，与参数化后的
    # q42_model.solve_horizon 口径不一致 → 误报失败。
    rolling = load_module(Q2_CODE / "rolling_window.py", "rolling_window")
    rolling.HERE = out
    apply_to_run1439(rolling.base, args.eff)
    print(f"  已覆盖 run_1439.ETA_C/D = {rolling.base.ETA_C:.6f}", flush=True)

    q42 = load_module(P2_CODE / "q42_model.py", "q42_model")
    q42.HERE = out
    q42.solve_horizon = make_solve_horizon(eta_c, eta_d)
    print("  已参数化 q42_model.solve_horizon（含约束矩阵）", flush=True)

    verify_mod, n_patch = load_verify_q42_with_eta(
        P2_CODE / "verify_q42.py", "verify_q42", eta_c, eta_d)
    verify_mod.HERE = out
    print(f"  已参数化 verify_q42 的 SOC 校验行（替换 {n_patch} 处）", flush=True)

    import numpy as np
    import pandas as pd

    # ---- 1) 独立物理 + 账目 + 工作簿校验 ----
    print("\n[1/5] 独立校验 verify_q42.verify_q42.main()", flush=True)
    verify_mod.main()
    ver = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    print(f"    verification pass_check = {ver['pass_check']}", flush=True)

    # ---- 2) 信息校验（未来扰动不得改变当前决策）----
    print("\n[2/5] 信息校验 q42_model.check_information", flush=True)
    ci = load_module(P2_CODE / "check_information.py", "check_information")
    # check_information 在模块级 `from q42_model import HERE, Inputs, solve_horizon, base, T`，
    # 已绑定参数化后的 solve_horizon 与 HERE，无需额外覆盖。
    ci.main()
    info = json.loads((out / "information_verification.json").read_text(encoding="utf-8"))
    print(f"    information pass_check = {info['pass_check']}", flush=True)

    # ---- 3) 月度对照 ----
    print("\n[3/5] 月度对照 monthly_comparison.csv", flush=True)
    comp = pd.read_csv(out / "comparison.csv")
    base_days = pd.read_csv(out / "variants" / "q2_repriced" / "daily_summary.csv")
    rows = []
    for _, r in comp.iterrows():
        frame = pd.read_csv(out / "variants" / r["name"] / "daily_summary.csv")
        ch = pd.DataFrame(dict(
            month=pd.to_datetime(frame.date).dt.month,
            cost_yuan=frame.total_cost_yuan.to_numpy(),
            saving_yuan=base_days.total_cost_yuan.to_numpy()
                        - frame.total_cost_yuan.to_numpy()))
        for month, g in ch.groupby("month").sum().iterrows():
            rows.append(dict(name=r["name"], month=int(month),
                             cost_yuan=float(g.cost_yuan),
                             saving_yuan=float(g.saving_yuan)))
    pd.DataFrame(rows).to_csv(out / "monthly_comparison.csv", index=False,
                              encoding="utf-8-sig")
    print(f"    monthly_comparison.csv  {len(rows)} 行", flush=True)

    # ---- 4) 发布到顶层 + 指定日期表 + 图 ----
    print("\n[4/5] 发布顶层文件、指定日期表与图", flush=True)
    report = load_module(P2_CODE / "report_q42.py", "report_q42")
    report.HERE = out
    report.main()

    # ---- 5) 发布核验 ----
    print("\n[5/5] 发布核验 publication_verification.json", flush=True)
    pub = json.loads((out / "publication_verification.json").read_text(encoding="utf-8"))
    pub["efficiency"] = eff_metadata(args.eff)
    missing = [n for n in ("result4-2.xlsx", "daily_summary.csv",
                           "schedule_detail.csv.gz") if not (out / n).exists()]
    pub["pass_check"] = bool(pub.get("pass_check")) and not missing
    (out / "publication_verification.json").write_text(
        json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 76)
    print(f"完成。pass={pub['pass_check']}")
    print(f"输出: {out}")
    if not pub["pass_check"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
