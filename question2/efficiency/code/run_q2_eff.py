"""问题2：两种效率口径的全年滚动优化（def1 往返 0.81 / def2 往返 0.90）。

做法
    复用 question2/code/run_experiment.py 的全部逻辑（预测器、场景、滚动、
    结算、导出），只在运行前把公共基础模块 run_1439.py 的 ETA_C / ETA_D
    覆盖为所选口径 —— **不修改任何原始文件**。

效率口径
    def1_side90        η_c = η_d = 0.90      往返 0.81（仓库原口径）
    def2_roundtrip90   η_c = η_d = √0.90     往返 0.90（国标口径）

用法
    python run_q2_eff.py --eff def1_side90
    python run_q2_eff.py --eff def2_roundtrip90

输出
    <repo>/question2/efficiency/<eff>/results/
        （与 question2/results/ 同构：result2.xlsx、daily_summary.csv、
          schedule_detail.csv.gz、summary.json、comparison.csv、
          variants/*、sensitivity/valid_residuals/* 等）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
Q2_CODE = REPO / "question2" / "code"
ETA_DIR = REPO / "common" / "efficiency"
sys.path.insert(0, str(ETA_DIR))
sys.path.insert(0, str(Q2_CODE))

from eta_common import (apply_to_run1439, check_q2_schedule, eff_metadata,  # noqa: E402
                        get_eff, results_dir)


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
    ap.add_argument("--out", default=None)
    ap.add_argument("--days", type=int, default=334)
    ap.add_argument("--skip-extended", action="store_true",
                    help="只跑主候选与有效残差组，跳过短窗口扩展（较省时）")
    ap.add_argument("--publish-only", action="store_true",
                    help="跳过求解，只把已有结果发布到顶层（修复/补发用）")
    args = ap.parse_args()

    eta_c, eta_d, rt, label, note = get_eff(args.eff)
    out = Path(args.out) if args.out else results_dir("question2", args.eff, REPO)
    out.mkdir(parents=True, exist_ok=True)
    if args.eff == "def1_side90" and not args.out:
        print("[提示] def1 与原定义逐值相同，直接写 question2/results，不生成副本")

    print("=" * 76)
    print(f"问题2  效率口径 = {args.eff}")
    print("=" * 76)
    print(f"  {label}")
    print(f"  {note}")
    print(f"  η_c = {eta_c:.6f}   η_d = {eta_d:.6f}   往返 = {rt:.6f}")
    print(f"  输出目录: {out}")
    print(flush=True)

    # ---- 载入并覆盖效率（在 importer 之前完成）----
    rolling = load_module(Q2_CODE / "rolling_window.py", "rolling_window")
    base = rolling.base
    apply_to_run1439(base, args.eff)
    print(f"  已覆盖 run_1439.ETA_C = {base.ETA_C:.6f}, "
          f"run_1439.ETA_D = {base.ETA_D:.6f}", flush=True)

    # rolling_window 顶部对 load_attachment1 做了 lru_cache 包装，
    # 覆盖 ETA 不影响预测器（预测器与效率无关），故无需重载。
    run_exp = load_module(Q2_CODE / "run_experiment.py", "run_experiment")

    t0 = time.time()
    vr = out / "sensitivity" / "valid_residuals"

    if args.publish_only:
        print("\n[publish-only] 跳过求解，直接发布已有结果", flush=True)
        publish(out, vr)
        verify(out, vr, eta_c, eta_d, args.eff)
        print(f"\n总耗时 {time.time() - t0:.1f}s")
        return

    # ---- 主组：原样口径（含回退残差，first_residual=0）----
    print("\n" + "-" * 76)
    print("[1/4] 主组：原样口径（含 1 月 1-7 日回退残差）")
    print("-" * 76, flush=True)
    _run(run_exp, out, first_residual=0, days=args.days,
         extended=not args.skip_extended)

    # ---- 第二组：剔除回退残差（最终采用口径）----
    print("\n" + "-" * 76)
    print("[2/4] 有效残差口径（first_residual=7）")
    print("-" * 76, flush=True)
    _run(run_exp, vr, first_residual=7, days=args.days, extended=False)

    # ---- 第三组：发布（生成顶层文件，供 Q4-2 使用）----
    print("\n" + "-" * 76)
    print("[3/4] 发布推荐方案到顶层")
    print("-" * 76, flush=True)
    publish(out, vr)

    # ---- 第四组：校验 + 汇总 ----
    print("\n" + "-" * 76)
    print("[4/4] 独立校验")
    print("-" * 76, flush=True)
    verify(out, vr, eta_c, eta_d, args.eff)

    print(f"\n总耗时 {time.time() - t0:.1f}s")
    print(f"输出目录: {out}")


def publish(out, vr):
    """把推荐方案（有效残差 + 56 天等权）发布到顶层，供 Q4-2 消费。

    复刻 question2/code/report_experiment.py 的发布动作，但**去掉**
    其中针对 def1 的「原基线必须精确等于 common/q2_base/summary.json」
    断言 —— 该断言只在 def1 下成立（def2 的基线本就不同）。

    产生/更新：schedule_detail.csv.gz、result2.xlsx、daily_summary.csv、
              summary.json（追加 recommended_variant 等字段）、all_comparisons.csv
    """
    import shutil

    import pandas as pd

    recommended = vr / "variants" / "uniform56"
    need = ["result2.xlsx", "daily_summary.csv", "schedule_detail.csv.gz"]
    for n in need:
        if not (recommended / n).exists():
            raise SystemExit(f"缺少推荐方案文件: {recommended / n}")
        shutil.copy2(recommended / n, out / n)

    summary = json.loads((recommended / "summary.json").read_text(encoding="utf-8"))
    summary.update(
        recommended_variant="sensitivity/valid_residuals/variants/uniform56",
        recommendation_reason="Use only genuine historical weekday forecasts: skip "
                              "Jan1-7 fallback residuals; keep original 56-day equal weights.",
    )
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 汇总三组对照（与 report_experiment.collect 同构）
    groups = [("原样本口径", out), ("短窗口扩展", out / "extensions" / "short_windows"),
              ("排除回退残差", vr)]
    rows = []
    for group, folder in groups:
        p = folder / "comparison.csv"
        if not p.exists():
            continue
        x = pd.read_csv(p)
        x["group"] = group
        x["relative_folder"] = [str((folder / "variants" / n).relative_to(out)).replace("\\", "/")
                                for n in x.name]
        rows.append(x)
    if rows:
        df = pd.concat(rows, ignore_index=True)
        base_p = out / "variants" / "uniform56" / "summary.json"
        if base_p.exists():
            baseline = json.loads(base_p.read_text(encoding="utf-8"))["total_cost_yuan"]
            df["saving_vs_original_yuan"] = baseline - df.total_cost_yuan
        df.to_csv(out / "all_comparisons.csv", index=False, encoding="utf-8-sig")
        print(f"  已发布顶层文件（{len(need)} 个）+ all_comparisons.csv（{len(df)} 行）")
    return summary


def _run(run_exp, out, first_residual, days, extended):
    """以指定参数调用 run_experiment.main()，输出写入 out。"""
    argv = ["run_experiment.py",
            "--first-residual", str(first_residual),
            "--days", str(days),
            "--out", str(out)]
    if extended:
        argv.append("--extended")
    old = sys.argv
    try:
        sys.argv = argv
        run_exp.main()
    finally:
        sys.argv = old


def verify(root, vr_root, eta_c, eta_d, eff_key):
    """对主组与有效残差组的关键输出做独立校验。"""
    import pandas as pd

    report = {}
    targets = {
        "primary_uniform56": root / "variants" / "uniform56",
        "valid_residuals_uniform56": vr_root / "variants" / "uniform56",
    }
    for tag, folder in targets.items():
        detail_p = folder / "schedule_detail.csv.gz"
        daily_p = folder / "daily_summary.csv"
        if not detail_p.exists() or not daily_p.exists():
            report[tag] = {"pass_check": False, "reason": "缺少输出文件"}
            continue
        detail = pd.read_csv(detail_p)
        daily = pd.read_csv(daily_p)
        res = check_q2_schedule(detail, daily, eta_c, eta_d)
        report[tag] = res
        status = "✓ 通过" if res["pass_check"] else "✗ 失败"
        print(f"  [{status}] {tag}")
        for k, v in res["errors"].items():
            print(f"        {k:34s} = {v}")

    (root / "efficiency_verification.json").write_text(
        json.dumps(dict(eta_charge=eta_c, eta_discharge=eta_d,
                        eta_roundtrip=eta_c * eta_d, checks=report),
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # 汇总关键费用
    print("\n  关键费用：")
    summary = {}
    for tag, folder in targets.items():
        sp = folder / "summary.json"
        if sp.exists():
            j = json.loads(sp.read_text(encoding="utf-8"))
            summary[tag] = j["total_cost_yuan"]
            print(f"        {tag:28s} {j['total_cost_yuan']:>16,.2f} 元  "
                  f"({j['total_cost_yuan'] / 1e4:.2f} 万)")
    (root / "efficiency_summary.json").write_text(
        json.dumps(dict(**eff_metadata(eff_key), costs=summary),
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    main()
