"""把队友 Q2 的优化思路系统应用到 Q3。

队友 Q2 结论（方案B_滚动窗口优化）
  · 最优 = **排除回退残差（first_residual=7）+ 56 天等权**（省 12,861.89 元）
  · 半衰期加权、在线选择、短窗口 **均无稳定收益**

队友 Q3 现状
  · q3_forecast.py 已内置 FIRST_RESIDUAL=7、WINDOW=56 → 已含 Q2 修正
  · 但 **未做 first_residual / 窗口 的敏感性分析**

本脚本在 Q3 上补做该系统扫描
  A. first_residual ∈ {0, 7}（0 = 含回退残差）
  B. WINDOW ∈ {42, 56, 70, 84}
  C. 二者组合
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE / "_peer_lab"
sys.path.insert(0, str(LAB))

import q3_data, q3_forecast, q3_model          # noqa: E402
import run_q3 as RUN                            # noqa: E402


def run(label, window=None, first_res=None, half_life=None):
    if window is not None:
        q3_forecast.WINDOW = window
    if first_res is not None:
        q3_forecast.FIRST_RESIDUAL = first_res
    f = q3_forecast.Forecaster(q3_data.load_data())
    if half_life is not None:
        # 重算 scenarios 的权重（指数衰减）
        _orig_scen = q3_forecast.Forecaster.scenarios

        def scen_decay(self, d, stage, source='fusion'):
            past = np.arange(max(q3_forecast.FIRST_RESIDUAL,
                                 d - q3_forecast.WINDOW), d)
            point = self.point(d, stage, source)[None, :T]
            if not len(past):
                return point, np.array([], dtype=int)
            resid = np.array([(self.data['load'][r] - self.data['pv'][r]) / 6
                              - self.point(r, stage, source)[:T] for r in past])
            return point + resid, past
        q3_forecast.Forecaster.scenarios = scen_decay
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    if half_life is not None:
        q3_forecast.Forecaster.scenarios = _orig_scen
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "A"
    res = {}
    if which == "A":
        res["基线(FIRST=7,W=56)"] = run("基线")
        res["FIRST=0(含回退)"] = run("FIRST=0", first_res=0)
    elif which == "B":
        res["W=42"] = run("W=42", window=42)
        res["W=70"] = run("W=70", window=70)
        res["W=84"] = run("W=84", window=84)
    elif which == "C":
        res["FIRST=0,W=84"] = run("FIRST=0,W=84", window=84, first_res=0)
        res["FIRST=14,W=56"] = run("FIRST=14,W=56", first_res=14)
    (HERE / f"_opt_q3target_{which}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<24}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-1402.24e4)/1e4:+6.2f}")
