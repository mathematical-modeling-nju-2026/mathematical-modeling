"""问题4-2：两种效率口径的波动电价日前调度（def1 往返 0.81 / def2 往返 0.90）。

做法
    复用 question4/part2 的全部逻辑（电价预测、联合场景、LP、结算、导出），
    只在运行前做三处运行期覆盖 —— **不修改任何原始文件**：

      ① common/q2_base/run_1439.py 的 ETA_C / ETA_D （1 月预热用）
      ② q42_model.solve_horizon                    （主模型，含硬编码 .81）
      ③ q42_model.HERE / BASE_DIR                  （输出与 Q2 基线指向本口径）

    BASE_DIR 指向**同口径**的问题2 结果，保证「Q2 重结算基线」与主模型
    使用同一套效率，避免混口径。

前置条件
    同口径的问题2 结果必须已存在：
        question2/efficiency/<eff>/results/{schedule_detail.csv.gz, summary.json,
                                            common_january.json}

用法
    python run_q42_eff.py --eff def1_side90
    python run_q42_eff.py --eff def2_roundtrip90

输出
    <repo>/question4/efficiency/<eff>/part2/results/
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
Q2_CODE = REPO / "question2" / "code"
P2_CODE = REPO / "question4" / "part2" / "code"
ETA_DIR = REPO / "common" / "efficiency"
sys.path.insert(0, str(ETA_DIR))
sys.path.insert(0, str(Q2_CODE))
sys.path.insert(0, str(P2_CODE))

from eta_common import apply_to_run1439, check_q2_schedule, eff_metadata  # noqa: E402
from eta_common import get_eff, make_solve_horizon, results_dir  # noqa: E402


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def ensure_q2_code_shim(q2_dir):
    """确保 <q2_dir>/../code/ 下存在 Q2 驱动文件（仅用于指纹比对）。

    run_q42.main() 会用
        BASE_DIR.parent/'code'/'rolling_window.py'  等路径做源文件指纹校验。
    当 BASE_DIR 指向 question2/results 时 parent 即 question2，天然满足；
    但指向 question2/efficiency/<eff>/results 时，parent 下没有 code/，
    会抛 FileNotFoundError。这里按原文件内容补齐**副本**，
    仅供哈希比对使用（不会被 import）。
    """
    shim = Path(q2_dir).parent / "code"
    src_dir = REPO / "question2" / "code"
    made = []
    for name in ("rolling_window.py", "run_experiment.py"):
        dst = shim / name
        if dst.exists():
            continue
        shim.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((src_dir / name).read_bytes())
        made.append(name)
    if made:
        print(f"  已补建指纹用副本: {shim} -> {', '.join(made)}", flush=True)
    return shim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eff", default="def1_side90",
                    choices=["def1_side90", "def2_roundtrip90"])
    ap.add_argument("--primary", default="joint_price",
                    choices=["joint_price", "known_today_price"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--q2-results", default=None,
                    help="同口径的问题2 结果目录；默认自动指向 efficiency/<eff>")
    args = ap.parse_args()

    eta_c, eta_d, rt, label, note = get_eff(args.eff)

    # ---- 输出目录与 Q2 基线目录（def1 = 仓库原结果，无副本）----
    out = Path(args.out) if args.out else results_dir("question4/part2", args.eff, REPO)
    out.mkdir(parents=True, exist_ok=True)

    if args.q2_results:
        q2_dir = Path(args.q2_results)
    else:
        q2_dir = results_dir("question2", args.eff, REPO)

    for need in ("schedule_detail.csv.gz", "summary.json", "common_january.json"):
        if not (q2_dir / need).exists():
            raise SystemExit(
                f"缺少同口径的问题2 结果: {q2_dir / need}\n"
                f"请先运行: python question2/efficiency/code/run_q2_eff.py --eff {args.eff}")

    print("=" * 76)
    print(f"问题4-2  效率口径 = {args.eff}")
    print("=" * 76)
    print(f"  {label}")
    print(f"  {note}")
    print(f"  η_c = {eta_c:.6f}   η_d = {eta_d:.6f}   往返 = {rt:.6f}")
    print(f"  Q2 基线目录 : {q2_dir}")
    print(f"  输出目录    : {out}")
    print(flush=True)

    # ---- ① 覆盖 run_1439 的效率（1 月预热）----
    rolling = load_module(Q2_CODE / "rolling_window.py", "rolling_window")
    base = rolling.base
    apply_to_run1439(base, args.eff)
    print(f"  ① 覆盖 run_1439.ETA_C/D = {base.ETA_C:.6f}", flush=True)
    ensure_q2_code_shim(q2_dir)

    # ---- ② 载入 q42_model 并覆盖 solve_horizon / HERE / BASE_DIR ----
    q42 = load_module(P2_CODE / "q42_model.py", "q42_model")
    q42.solve_horizon = make_solve_horizon(eta_c, eta_d)
    q42.HERE = out
    q42.BASE_DIR = q2_dir
    print(f"  ② 覆盖 q42_model.solve_horizon（含约束矩阵与投影，往返 .81 → {rt:.4f}）",
          flush=True)
    print(f"  ③ 覆盖 q42_model.HERE / BASE_DIR", flush=True)

    # ---- ③ 载入 run_q42 并运行 ----
    run_q42 = load_module(P2_CODE / "run_q42.py", "run_q42")
    # run_q42 在模块级 `from q42_model import HERE, BASE_DIR, ...`
    # 由于上一步已覆盖 q42_model 的属性，此处绑定的是新值。
    assert Path(run_q42.HERE) == out, "HERE 未生效"
    assert Path(run_q42.BASE_DIR) == q2_dir, "BASE_DIR 未生效"

    t0 = time.time()
    argv = ["run_q42.py", "--primary", args.primary]
    old = sys.argv
    try:
        sys.argv = argv
        run_q42.main()
    finally:
        sys.argv = old

    # ---- 校验（用参数化效率）----
    print("\n" + "-" * 76)
    print("独立复核（使用实际 η_c / η_d）")
    print("-" * 76, flush=True)
    import pandas as pd
    rep = {}
    for name in ("q2_repriced", "mean_price", "joint_price", "known_today_price"):
        dp = out / "variants" / name / "schedule_detail.csv.gz"
        yp = out / "variants" / name / "daily_summary.csv"
        if not dp.exists():
            continue
        res = check_q2_schedule(pd.read_csv(dp), pd.read_csv(yp), eta_c, eta_d)
        rep[name] = res
        print(f"  [{'✓ 通过' if res['pass_check'] else '✗ 失败'}] {name}")
        if not res["pass_check"]:
            for k, v in res["errors"].items():
                print(f"        {k:34s} = {v}")

    (out / "efficiency_verification.json").write_text(
        json.dumps(dict(**eff_metadata(args.eff), checks=rep),
                   ensure_ascii=False, indent=2), encoding="utf-8")

    cmp_p = out / "comparison.csv"
    if cmp_p.exists():
        c = pd.read_csv(cmp_p)
        print("\n  各方案总费用：")
        for _, r in c.iterrows():
            print(f"        {r['name']:20s} {r['total_cost_yuan']:>16,.2f} 元  "
                  f"({r['total_cost_yuan'] / 1e4:.2f} 万)")
        main_row = c[c["name"] == args.primary]
        if len(main_row):
            (out / "efficiency_summary.json").write_text(
                json.dumps(dict(**eff_metadata(args.eff),
                                primary=args.primary,
                                total_cost_yuan=float(main_row.iloc[0]["total_cost_yuan"]),
                                emergency_kwh=float(main_row.iloc[0]["emergency_kwh"])),
                           ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n总耗时 {time.time() - t0:.1f}s")
    print(f"输出目录: {out}")


if __name__ == "__main__":
    main()
