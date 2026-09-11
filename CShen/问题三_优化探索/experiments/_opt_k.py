"""关键实验：残差场景缩放系数 k。

原理
  场景 = 点预测 + k × 历史残差。k 直接控制"感知不确定性"：
    k < 1 → 计划更激进（少备货，靠调整/紧急兜底）
    k > 1 → 计划更保守（多备货，弃置多）
  在报童型结构下，这等价于**直接调节有效分位**，比"放松下界"更自然
  （下界放松只改约束、不改场景，已被证明无效）。

这是同伴未做敏感性分析、且理论上最重要的参数。
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

T = q3_data.T
_ORIG_SCEN = q3_forecast.Forecaster.scenarios


def make_scen(k):
    def scenarios(self, d, stage, source='fusion'):
        point, past = _ORIG_SCEN(self, d, stage, source)
        if k == 1.0:
            return point, past
        base = self.point(d, stage, source)[:T]
        return base[None, :] + k * (point - base[None, :]), past
    return scenarios


def run(label, k):
    q3_forecast.Forecaster.scenarios = make_scen(k)
    f = q3_forecast.Forecaster(q3_data.load_data())
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    q3_forecast.Forecaster.scenarios = _ORIG_SCEN
    print(f"[k={k:<5}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "1"
    KS = {"1": [1.0, 0.9], "2": [0.8, 0.7], "3": [1.1, 1.2], "4": [0.95, 0.85]}
    res = {}
    for k in KS[which]:
        res[str(k)] = run(k, k)
    (HERE / f"_opt_k_{which}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
