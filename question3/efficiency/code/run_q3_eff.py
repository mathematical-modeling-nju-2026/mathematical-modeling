"""问题3：两种效率口径的全年场景树优化（def1 往返 0.81 / def2 往返 0.90）。

做法
    复用 question3/code/run_q3.py 的全部逻辑（预测、场景树、跨日滚动、
    分项结算、导出、校验），只在运行前把 q3_model 的 ETA 覆盖为所选口径
    —— **不修改任何原始文件**。

效率口径
    def1_side90        ETA = 0.90      往返 0.81（仓库原口径）
    def2_roundtrip90   ETA = √0.90     往返 0.90（国标口径）

    注：q3_model 用 `ETA**2` 表示往返效率清理同时充放电，
    对称拆分下 (√0.9)**2 = 0.9 恰好等于往返效率，故只需覆盖 ETA 一个量。

用法
    python run_q3_eff.py --eff def1_side90 --mode all
    python run_q3_eff.py --eff def2_roundtrip90 --mode suite

输出
    <repo>/question3/efficiency/<eff>/results/
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
Q3_CODE = REPO / "question3" / "code"
ETA_DIR = REPO / "common" / "efficiency"
sys.path.insert(0, str(ETA_DIR))
sys.path.insert(0, str(Q3_CODE))

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
    out = Path(args.out) if args.out else results_dir("question3", args.eff, REPO)
    out.mkdir(parents=True, exist_ok=True)
    if args.eff == "def1_side90" and not args.out:
        print("[提示] def1 与原定义逐值相同，直接写 question3/results，不生成副本")

    print("=" * 76)
    print(f"问题3  效率口径 = {args.eff}")
    print("=" * 76)
    print(f"  {label}")
    print(f"  {note}")
    print(f"  ETA = {eta_c:.6f}   往返 = {rt:.6f}")
    print(f"  输出目录: {out}")
    print(flush=True)

    # ---- 覆盖 ETA（必须在 run_q3 导入 q3_model 之后、调用 main 之前）----
    # run_q3.py 在模块级 `from q3_model import solve, E_INIT`，但 solve()
    # 内部读取的是 q3_model 模块的全局 ETA，故覆盖模块属性即可生效。
    q3_model = load_module(Q3_CODE / "q3_model.py", "q3_model")
    apply_to_q3_model(q3_model, args.eff)
    print(f"  已覆盖 q3_model.ETA = {q3_model.ETA:.6f} "
          f"(往返 {q3_model.ETA ** 2:.6f})", flush=True)

    # q3_model 被 run_q3 / verify_q3 共同导入，保证校验用同一口径。
    # run_q3.main() 每次求解后调用 verify_q3.check_schedule 强制校验；
    # 原版把 0.9 写死，def2 下会误报。这里用**源码文本替换**的方式
    # （仅改 .9*c / d/.9 两处常量），保留原校验的全部其余逻辑。
    run_q3 = load_module(Q3_CODE / "run_q3.py", "run_q3")
    verify_q3, n_sub = load_verify_with_eta(
        Q3_CODE / "verify_q3.py", "verify_q3", eta_c, eta_d)
    if n_sub == 0:
        raise SystemExit("未能将 verify_q3 的效率常量参数化，请检查源码")
    sys.modules["verify_q3"] = verify_q3
    print(f"  已参数化 verify_q3.check_schedule（替换 {n_sub} 处）", flush=True)

    t0 = time.time()
    argv = ["run_q3.py", "--mode", args.mode,
            "--days", str(args.days), "--out", str(out)]
    old = sys.argv
    try:
        sys.argv = argv
        run_q3.main()
    finally:
        sys.argv = old

    # ---- 用参数化效率复校（原 verify_q3 硬编码 0.9）----
    # 直接用「只改了效率常量的原版校验函数」，避免重写逻辑引入口径漂移。
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
                  "cost_recomputed_yuan",
                  "alternative_no_refund_cost_same_schedule_yuan"):
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
