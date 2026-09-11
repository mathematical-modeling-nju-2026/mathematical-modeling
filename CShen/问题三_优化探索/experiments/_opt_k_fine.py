"""精调 k + 终端条件实验。

发现：k=0.9（场景缩放）→ 1401.82 万，优于基线 1402.24。
机理：k<1 相当于下调"感知不确定性"→ 计划更激进（少备货）→ 靠调整/紧急兜底。
      k=0.9 时计划费 −11.25 万、紧急费 +9.84 万，净省 0.42 万。

本脚本
  A. 精调全局 k ∈ {0.95, 0.92, 0.88, 0.85}
  B. 分时段 k（首块不可调整 → 应更保守 k 大；后续可调整 → k 小）
  C. 终端条件 E_term 变化（次日留存更多电量）
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
_ORIG = q3_forecast.Forecaster.scenarios


def make_scen_global(k):
    def scen(self, d, stage, source='fusion'):
        point, past = _ORIG(self, d, stage, source)
        base = self.point(d, stage, source)[:T]
        return base[None, :] + k * (point - base[None, :]), past
    return scen


def make_scen_blocked(k_head, k_tail, n_head=36):
    """首 n_head 段（不可调整）用 k_head，之后用 k_tail。"""
    def scen(self, d, stage, source='fusion'):
        point, past = _ORIG(self, d, stage, source)
        base = self.point(d, stage, source)[:T]
        kk = np.full(T, k_tail)
        kk[:n_head] = k_head
        return base[None, :] + kk[None, :] * (point - base[None, :]), past
    return scen


def make_scen_stage(k_by_stage):
    """按 stage 给不同 k（列表 4 个）。"""
    def scen(self, d, stage, source='fusion'):
        point, past = _ORIG(self, d, stage, source)
        base = self.point(d, stage, source)[:T]
        return base[None, :] + k_by_stage[stage] * (point - base[None, :]), past
    return scen


def run(label, scen_fn=None, term_mult=None):
    if scen_fn is not None:
        q3_forecast.Forecaster.scenarios = scen_fn
    f = q3_forecast.Forecaster(q3_data.load_data())
    if term_mult is not None:
        # 让次日终端 = term_mult × day_start_energy
        orig_solve = q3_model.solve

        def patched(forecaster, day, stage, stages, energy, day_start_energy,
                    original=None, source='fusion', deterministic=False,
                    branch=True):
            return orig_solve(forecaster, day, stage, stages, energy,
                              term_mult * day_start_energy, original, source,
                              deterministic, branch)
        q3_model.solve = patched
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    if term_mult is not None:
        q3_model.solve = orig_solve
    q3_forecast.Forecaster.scenarios = _ORIG
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
        for k in (0.95, 0.92, 0.88, 0.85):
            res[f"k={k}"] = run(f"k={k}", make_scen_global(k))
    elif which == "B":
        res["k_head1.0,tail0.9"] = run("首块1.0/尾0.9",
                                       make_scen_blocked(1.0, 0.9))
        res["k_head1.0,tail0.85"] = run("首块1.0/尾0.85",
                                        make_scen_blocked(1.0, 0.85))
        res["k_head1.05,tail0.9"] = run("首块1.05/尾0.9",
                                        make_scen_blocked(1.05, 0.9))
    elif which == "C":
        res["E_term=1.1x"] = run("终端 1.1×", term_mult=1.1)
        res["E_term=0.95x"] = run("终端 0.95×", term_mult=0.95)
    (HERE / f"_opt_k{which}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<22}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-1402.24e4)/1e4:+6.2f}")
