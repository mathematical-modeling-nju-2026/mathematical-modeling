"""在同伴框架上做优化实验（不改其原文件，仅在副本上重算融合预报后跑 simulate）。

可调项
  · alpha_hi : α 上界（原版 1.0；>1 允许"放大"发布预报的反应强度）
  · shrink   : 偏差收缩系数（原版 14）
  · window   : 拟合窗口天数（原版 56）
  · sub      : 子块长度（原版 36 = 6h）
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


def rebuild_fused(f, window=56, shrink=14, alpha_hi=1.0, sub=36, alpha_lo=0.0):
    """按给定超参重算 f.alpha / f.fused（与原逻辑同构，仅参数不同）。"""
    flat = f.data['pv'].ravel()
    n = len(f.data['load'])
    fused = f.fused.copy()
    for s in range(4):
        start = s * 36
        for d in range(n):
            out = f.raw[d, s].copy()
            past = np.arange(max(q3_forecast.FIRST_RESIDUAL, d - window),
                             max(q3_forecast.FIRST_RESIDUAL, d - 1))
            if len(past) < 7:
                fused[d, s] = np.maximum(out, 0)
                continue
            y = np.array([flat[r * T + start: r * T + start + T] for r in past])
            ext = f.raw[past, s, start:start + T]
            hist = f.hist[past, start:start + T]
            for b in range(4):
                sl = slice(b * sub, (b + 1) * sub)
                delta = ext[:, sl] - hist[:, sl]
                den = float((delta * delta).sum())
                a = (float(np.clip((delta * (y[:, sl] - hist[:, sl])).sum() / den,
                                   alpha_lo, alpha_hi)) if den > 1e-9 else 1.0)
                old = a * ext[:, sl] + (1 - a) * hist[:, sl]
                bias = (y[:, sl] - old).mean(0) * len(past) / (len(past) + shrink)
                dst = slice(start + b * sub, start + (b + 1) * sub)
                out[dst] = a * f.raw[d, s, dst] + (1 - a) * f.hist[d, dst] + bias
            fused[d, s] = np.maximum(out, 0)
    return fused


def run_cfg(label, **kw):
    data = q3_data.load_data()
    f = q3_forecast.Forecaster(data)
    f.fused = rebuild_fused(f, **kw)
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "A"
    CFGS = {
        "A": [("基线(α≤1,s14,w56)", dict()),
              ("α≤1.25", dict(alpha_hi=1.25)),
              ("α≤1.5", dict(alpha_hi=1.5)),
              ("α≤1.25,s28", dict(alpha_hi=1.25, shrink=28))],
        "B": [("w28", dict(window=28)),
              ("w84", dict(window=84)),
              ("w112", dict(window=112)),
              ("s7", dict(shrink=7)),
              ("s28", dict(shrink=28))],
        "C": [("α≤1.25,w84", dict(alpha_hi=1.25, window=84)),
              ("α≤1.25,w112", dict(alpha_hi=1.25, window=112)),
              ("α≤1.5,w112", dict(alpha_hi=1.5, window=112)),
              ("sub=72(12h块)", dict(sub=72))],
    }
    res = {}
    for lab, kw in CFGS[which]:
        res[lab] = run_cfg(lab, **kw)
    (HERE / f"_opt_cfg_{which}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
