"""正确测试：降低 0:00 计划中"可调整时段"的紧急兜底罚系数。

重要修正
  之前 _exp_tail.py 无效，是因为只 patch 了 q3_model.solve，
  而 run_q3.py 通过 `from q3_model import solve` 持有**独立引用**。
  本脚本同时 patch q3_model.solve 与 RUN.solve。

理论依据（报童型临界分位）
  0:00 计划的有效分位 = c_o / (c_o + c_u)
    · 可调减（退款 0.5p）→ c_o = 0.5p
    · 首 6h 不可调整 → 缺口只能 5p 紧急购电 → c_u = 5p  → 分位 = 9.1%
      ... 即应几乎不备货（因为 5p 太贵，宁可少买？）——需实测
    · 6:00 后可调整 → 缺口可用 1.5p 调增 → c_u = 1.5p → 分位 = 25%
    · 但对称地看：多买的成本也是 0.5p（弃置损失），少买的成本是上面的 c_u
    对"可调整段"：多买 1kWh 的成本 = p（买）+ (-0.5p)（可退款）... 见报告推导。
  无论精确值如何，**可调整段的兜底罚应显著低于 5p**，这是确定的方向。
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

ORIG = q3_model.solve


def make_patched(tail_mult, tail_from=36):
    def patched(forecaster, day, stage, stages, energy, day_start_energy,
                original=None, source='fusion', deterministic=False,
                branch=True):
        return ORIG(forecaster, day, stage, stages, energy, day_start_energy,
                    original, source, deterministic, branch,
                    tail_emg_mult=tail_mult, tail_from=tail_from)
    return patched


def run(label, tail_mult, tail_from=36):
    p = make_patched(tail_mult, tail_from)
    q3_model.solve = p          # 供模块内其他调用
    RUN.solve = p               # ★ 关键：RUN.simulate 实际用的是这个
    f = q3_forecast.Forecaster(q3_data.load_data())
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    RUN.solve = ORIG
    q3_model.solve = ORIG
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "1"
    SEQ = {"1": [5.0, 2.0], "2": [1.5, 1.2], "3": [0.8, 0.5]}
    res = {}
    for tm in SEQ[which]:
        res[f"tail={tm}"] = run(f"tail_mult={tm}", tm)
    (HERE / f"_opt_tail_fix_{which}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
