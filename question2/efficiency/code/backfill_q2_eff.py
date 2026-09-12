"""问题2 效率口径补齐：对已有运行结果做独立校验 + 发布 + 指定日期表。

不重跑优化，只补齐缺失的交付物：
  · verification.json / information_verification.json / verification_all.json
  · monthly_savings.csv
  · target_table1/2/3.csv、target_daily.csv
  · extensions/short_windows 路径重定向后重新发布 all_comparisons.csv
  · source_fingerprints.json（效率口径专用，记录实际使用的 eta）
  · figures/window_comparison.png|pdf

关键做法（不修改任何原始文件）：
  1. 用 `run_q2_eff.py --publish-only --out <eff>/results` 复用其 publish()，
     但那里的 publish() 不写校验文件；因此本脚本自行编排。
  2. rolling_window.HERE / run_experiment.HERE 指向 <eff>/results
  3. verify_window.HERE 指向 <eff>/results，并用各口径实际的 expected_initial
  4. report_experiment.HERE 指向 <eff>/results，但跳过其 def1 专用断言
     （"原基线必须精确等于 common/q2_base/summary.json"）——该断言在 def2 不成立。

用法
    python backfill_q2_eff.py --eff def1_side90
    python backfill_q2_eff.py --eff def2_roundtrip90
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
ETA_DIR = REPO / "common" / "efficiency"
sys.path.insert(0, str(ETA_DIR))
sys.path.insert(0, str(Q2_CODE))

from eta_common import (eff_metadata as _base_eff_metadata, get_eff,  # noqa: E402
                        load_verify_window_with_eta, results_dir)


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
    out = results_dir("question2", args.eff, REPO)
    vr = out / "sensitivity" / "valid_residuals"
    ext = out / "extensions" / "short_windows"
    if not (out / "schedule_detail.csv.gz").exists():
        raise SystemExit(f"缺少已运行结果: {out}")

    print("=" * 76)
    print(f"问题2 补齐交付物  效率口径 = {args.eff}")
    print("=" * 76)
    print(f"  {label}")
    print(f"  η_c={eta_c:.6f} η_d={eta_d:.6f} 往返={rt:.6f}")
    print(f"  输出目录: {out}", flush=True)

    # ---------- 0) 重定向各模块的输出根 ----------
    rolling = load_module(Q2_CODE / "rolling_window.py", "rolling_window")
    rolling.HERE = out
    # verify_window.py 把 0.9 效率写死在 SOC 校验行，必须参数化后再用
    verify_mod, n_patch = load_verify_window_with_eta(
        Q2_CODE / "verify_window.py", "verify_window", eta_c, eta_d)
    verify_mod.HERE = out
    print(f"  已参数化 verify_window 的 SOC 校验行（替换 {n_patch} 处）", flush=True)
    report = load_module(Q2_CODE / "report_experiment.py", "report_experiment")
    report.HERE = out

    import numpy as np
    import pandas as pd

    # ---------- 1) 独立校验：主组 + 有效残差组 ----------
    print("\n[1/6] 独立校验（verify_window.check_schedule / check_workbook）", flush=True)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    expected_initial = float(summary["initial_energy_kwh"])
    raw_dir = REPO / "data"

    reports: dict = {}
    for group, folder in [("primary", out), ("valid_residuals", vr),
                          ("short_windows", ext)]:
        if not folder.exists():
            continue
        variants = {}
        for variant in sorted((folder / "variants").glob("*")):
            dp, yp = variant / "schedule_detail.csv.gz", variant / "daily_summary.csv"
            if not (dp.exists() and yp.exists()):
                continue
            detail, daily = pd.read_csv(dp), pd.read_csv(yp)
            rep = {"schedule": verify_mod.check_schedule(detail, daily,
                                                         expected_initial, raw_dir)}
            wb = variant / "result2.xlsx"
            if wb.exists():
                rep["workbook"] = verify_mod.check_workbook(wb, detail)
            rep["pass"] = all(v["pass"] for v in rep.values())
            variants[variant.name] = rep
            print(f"    {group:15s} {variant.name:15s} "
                  f"{'PASS' if rep['pass'] else 'FAIL'}", flush=True)
        res = {"pass": bool(variants) and all(v["pass"] for v in variants.values()),
               "expected_initial_kwh": expected_initial, "variants": variants}
        (folder / "verification.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        reports[group] = res

    # ---------- 2) 信息校验（check_information）----------
    print("\n[2/6] 信息校验（未来扰动不得改变当前决策）", flush=True)
    ci = load_module(Q2_CODE / "check_information.py", "check_information")
    ci.HERE = out
    ci.main()
    info = json.loads((out / "information_verification.json").read_text(encoding="utf-8"))

    # ---------- 3) monthly_savings.csv + 月度分解 ----------
    print("\n[3/6] 月度节省分解", flush=True)
    comp_p = out / "comparison.csv"
    comp = pd.read_csv(comp_p)
    base_variant = "uniform56"
    base_days = pd.read_csv(out / "variants" / base_variant / "daily_summary.csv")
    monthly = []
    for _, row in comp.iterrows():
        d = pd.read_csv(out / "variants" / row["name"] / "daily_summary.csv")
        m = pd.DataFrame({
            "month": pd.to_datetime(d.date).dt.month,
            "saving_yuan": base_days.total_cost_yuan.to_numpy()
                           - d.total_cost_yuan.to_numpy(),
        })
        for month, g in m.groupby("month").sum().iterrows():
            monthly.append(dict(group="原样本口径", name=row["name"],
                                month=int(month), saving_yuan=float(g.saving_yuan)))
    pd.DataFrame(monthly).to_csv(out / "monthly_savings.csv", index=False,
                                 encoding="utf-8-sig")
    print(f"    monthly_savings.csv  {len(monthly)} 行", flush=True)

    # ---------- 4) all_comparisons.csv（三组口径）----------
    print("\n[4/6] 三组对照汇总 all_comparisons.csv", flush=True)
    groups = [("原样本口径", out), ("短窗口扩展", ext), ("排除回退残差", vr)]
    rows = []
    for group, folder in groups:
        p = folder / "comparison.csv"
        if not p.exists():
            print(f"    跳过（缺 comparison.csv）: {folder}")
            continue
        x = pd.read_csv(p)
        x["group"] = group
        x["relative_folder"] = [
            str((folder / "variants" / n).relative_to(out)).replace("\\", "/")
            for n in x.name]
        rows.append(x)
    if rows:
        df = pd.concat(rows, ignore_index=True)
        base_cost = float(json.loads(
            (out / "variants" / base_variant / "summary.json")
            .read_text(encoding="utf-8"))["total_cost_yuan"])
        df["saving_vs_original_yuan"] = base_cost - df.total_cost_yuan
        df.to_csv(out / "all_comparisons.csv", index=False, encoding="utf-8-sig")
        print(f"    all_comparisons.csv  {len(df)} 行，组={sorted(df.group.unique())}",
              flush=True)

    # ---------- 5) 指定日期表（表1/表2/表3）----------
    print("\n[5/6] 题目指定日期表 表1/表2/表3", flush=True)
    mt = load_module(Q2_CODE / "make_target_tables.py", "make_target_tables")
    mt.RES = out
    mt.DETAIL = out / "schedule_detail.csv.gz"
    mt.main()

    # ---------- 6) 发布校验汇总 + 源指纹（口径化）----------
    print("\n[6/6] 发布校验汇总 verification_all.json", flush=True)
    bundle = {k: v for k, v in reports.items()}
    bundle["information"] = info
    # 该口径不必复现 common/q2_base 的原基线（那是 def1 专属事实）
    deps = [rolling.SOURCE, REPO / "common" / "q2_base" / "q2_data.py"]
    deps += [REPO / "data" / "附件" / f"附件{i}.xlsx" for i in (1, 2)]
    bundle["source_fingerprints_sha256"] = {
        str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in deps}
    (out / "source_fingerprints.json").write_text(
        json.dumps(bundle["source_fingerprints_sha256"], ensure_ascii=False, indent=2),
        encoding="utf-8")
    (out / "source_fingerprints.migrated.json").write_text(
        json.dumps(bundle["source_fingerprints_sha256"], ensure_ascii=False, indent=2),
        encoding="utf-8")
    bundle["efficiency"] = eff_metadata(args.eff)
    bundle["published_file_hashes"] = {
        n: hashlib.sha256((out / n).read_bytes()).hexdigest()
        for n in ("result2.xlsx", "daily_summary.csv") if (out / n).exists()}
    bundle["published_files_identical_to_verified_variant"] = all(
        (out / n).read_bytes() == (vr / "variants" / base_variant / n).read_bytes()
        for n in ("result2.xlsx", "daily_summary.csv")
        if (out / n).exists())
    bundle["pass"] = (all(r.get("pass") for r in reports.values())
                      and info.get("pass_check") is True
                      and bundle["published_files_identical_to_verified_variant"])
    (out / "verification_all.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 76)
    print(f"完成。pass={bundle['pass']}")
    print(f"输出: {out}")
    if not bundle["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
