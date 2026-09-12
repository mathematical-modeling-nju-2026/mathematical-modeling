"""问题4-3：两种效率口径的波动电价 + 多时点调整（def1 0.81 / def2 0.90）。

做法
    复用 question4/part3 的全部逻辑，只在运行前做运行期覆盖
    —— **不修改任何原始文件**：

      ① 环境变量 CUMCM_C_ATTACHMENT_DIR 指向仓库 data/附件
         （part3 的 q3_data.attachment_dir() 按 parents[2] 推断，
           在 efficiency/<eff>/part3/results 深度下会失效）
      ② question4/part3/code/q3_model.py 的 ETA
      ③ verify_q3.check_schedule 换为参数化效率版本

效率口径
    def1_side90        ETA = 0.90      往返 0.81（仓库原口径）
    def2_roundtrip90   ETA = √0.90     往返 0.90（国标口径）

用法
    python run_q43_eff.py --eff def1_side90 --mode suite
    python run_q43_eff.py --eff def2_roundtrip90 --mode all

输出
    <repo>/question4/efficiency/<eff>/part3/results/
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
P3_CODE = REPO / "question4" / "part3" / "code"
ETA_DIR = REPO / "common" / "efficiency"

# ---- ① 必须在导入 q3_data 之前设置附件目录 ----
os.environ.setdefault("CUMCM_C_ATTACHMENT_DIR", str(REPO / "data" / "附件"))

sys.path.insert(0, str(ETA_DIR))
sys.path.insert(0, str(P3_CODE))

from eta_common import (apply_to_q3_model, check_charge_schedule,  # noqa: E402
                        eff_metadata, get_eff, load_verify_with_eta, results_dir)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eff", default="def1_side90",
                    choices=["def1_side90", "def2_roundtrip90"])
    ap.add_argument("--mode", default="suite",
                    choices=["B_aligned", "only_0", "at_0_6", "at_0_6_12",
                             "all", "suite"])
    ap.add_argument("--days", type=int, default=334)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    eta_c, eta_d, rt, label, note = get_eff(args.eff)
    out = Path(args.out) if args.out else results_dir("question4/part3", args.eff, REPO)
    out.mkdir(parents=True, exist_ok=True)
    if args.eff == "def1_side90" and not args.out:
        print("[提示] def1 与原定义逐值相同，直接写 question4/part3/results，不生成副本")

    print("=" * 76)
    print(f"问题4-3  效率口径 = {args.eff}")
    print("=" * 76)
    print(f"  {label}")
    print(f"  {note}")
    print(f"  ETA = {eta_c:.6f}   往返 = {rt:.6f}")
    print(f"  附件目录: {os.environ['CUMCM_C_ATTACHMENT_DIR']}")
    print(f"  输出目录: {out}")
    print(flush=True)

    # ---- ② 覆盖 q3_model.ETA ----
    q3_model = load_module(P3_CODE / "q3_model.py", "q3_model")
    apply_to_q3_model(q3_model, args.eff)
    print(f"  ② 已覆盖 q3_model.ETA = {q3_model.ETA:.6f} "
          f"(往返 {q3_model.ETA ** 2:.6f})", flush=True)

    # ---- ③ 参数化校验函数（run_q3 会强制调用）----
    # 用**源码文本替换**：4-3 的 verify_q3 用 data['price_rt'] 实时电价结算，
    # 与 Q3 版本不同，故不能重写通用校验，只能改那两处效率常量。
    run_q3 = load_module(P3_CODE / "run_q3.py", "run_q3")
    verify_q3, n_sub = load_verify_with_eta(
        P3_CODE / "verify_q3.py", "verify_q3", eta_c, eta_d)
    if n_sub == 0:
        raise SystemExit("未能将 verify_q3 的效率常量参数化，请检查源码")
    sys.modules["verify_q3"] = verify_q3
    print(f"  ③ 已参数化 verify_q3.check_schedule（替换 {n_sub} 处）", flush=True)

    t0 = time.time()
    argv = ["run_q3.py", "--mode", args.mode,
            "--days", str(args.days), "--out", str(out)]
    old = sys.argv
    try:
        sys.argv = argv
        run_q3.main()
    finally:
        sys.argv = old

    # ---- 复核 ----
    # 直接用「只改了效率常量的原版校验函数」（4-3 用 data['price_rt'] 结算，
    # 与 Q3 版本不同，不能用通用校验函数）。
    print("\n" + "-" * 76)
    print("独立复核（使用实际 η_c / η_d）")
    print("-" * 76, flush=True)
    import pandas as pd
    data = run_q3.load_data()
    rep = {}
    for tag, folder in [("all", out), ("at_0_6_12", out / "comparisons" / "at_0_6_12")]:
        dp, yp = folder / "schedule_detail.csv", folder / "daily_summary.csv"
        if not dp.exists() or not yp.exists():
            continue
        res = verify_q3.check_schedule(pd.read_csv(dp), pd.read_csv(yp), data,
                                       require_year_end=(args.days >= 334))
        rep[tag] = res
        print(f"  [{'✓ 通过' if res['pass'] else '✗ 失败'}] {tag}")
        for k in ("energy_recursion_max_error", "energy_balance_max_error",
                  "simultaneous_periods", "settlement_per_slot_max_error",
                  "cost_recomputed_yuan"):
            print(f"        {k:44s} = {res[k]}")

    (out / "efficiency_verification.json").write_text(
        json.dumps(dict(**eff_metadata(args.eff), checks=rep),
                   ensure_ascii=False, indent=2), encoding="utf-8")

    sp = out / "summary.json"
    if sp.exists():
        j = json.loads(sp.read_text(encoding="utf-8"))
        print(f"\n  主方案总费用 = {j['total_cost_yuan']:,.2f} 元 "
              f"({j['total_cost_yuan'] / 1e4:.2f} 万)")
        (out / "efficiency_summary.json").write_text(
            json.dumps(dict(**eff_metadata(args.eff),
                            total_cost_yuan=j["total_cost_yuan"],
                            emergency_kwh=j.get("emergency_kwh")),
                       ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n总耗时 {time.time() - t0:.1f}s")
    print(f"输出目录: {out}")


if __name__ == "__main__":
    main()
