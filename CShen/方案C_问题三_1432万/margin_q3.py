"""问题3 边际分析：调整时点数量的收益 & 完美预见上界。

回答题目"请分析是否需要引入其他时刻的预报制定调整购电策略"。
- 方案A：不调整（仅 0:00 计划）
- 方案B：在 6/12/18 调整（题目给定）
- 方案C：加密调整时点（每 3 小时 / 每 1 小时）
- 上界 ：完美预见调整（知道当日实际）
"""
from __future__ import annotations
import sys, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import run_q3 as R


def total_for(**kw):
    r = R.simulate(verbose=False, **kw)
    s = R.summarize(r)
    return s


if __name__ == "__main__":
    out = {}
    print("跑：方案A 不调整 ...")
    out["A_no_adjust"] = total_for(use_adjust=False)
    print("跑：方案B 6/12/18 ...")
    out["B_3stages"] = total_for(use_adjust=True, adjust_stages=(1, 2, 3))
    print("跑：方案B' 仅 6:00 ...")
    out["B1_only6"] = total_for(use_adjust=True, adjust_stages=(1,))
    print("跑：方案B'' 6/12 ...")
    out["B2_6_12"] = total_for(use_adjust=True, adjust_stages=(1, 2))
    print("跑：上界 完美预见 ...")
    out["U_perfect"] = total_for(use_adjust=True, adjust_stages=(1, 2, 3),
                                 scen_mode="perfect")

    print()
    print("=" * 74)
    print(f"{'方案':<34}{'计划费':>10}{'调整费':>10}{'紧急费':>10}{'合计(万)':>12}")
    for k, s in out.items():
        print(f"{k:<34}{s['plan_cost']/1e4:>10.2f}{s['dev_cost']/1e4:>10.2f}"
              f"{s['emg_cost']/1e4:>10.2f}{s['total_wan']:>12.2f}")
    print("=" * 74)
    a = out["A_no_adjust"]["total"]
    print(f"\n相对不调整的节省（万元）：")
    for k, s in out.items():
        if k == "A_no_adjust":
            continue
        print(f"  {k:<28}{(a - s['total'])/1e4:>8.2f}")
    (HERE / "_q3_margin.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
