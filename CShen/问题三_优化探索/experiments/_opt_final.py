"""最终确认：最优配置（W=84, shrink=28, α≤1.25）与基线的完整对比。"""
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


def rebuild(f, shrink=14, alpha_hi=1.0, wfit=56):
    flat = f.data['pv'].ravel()
    n = len(f.data['load'])
    for s in range(4):
        start = s * 36
        for d in range(n):
            out = f.raw[d, s].copy()
            past = np.arange(max(q3_forecast.FIRST_RESIDUAL, d - wfit),
                             max(q3_forecast.FIRST_RESIDUAL, d - 1))
            if len(past) < 7:
                f.fused[d, s] = np.maximum(out, 0); continue
            y = np.array([flat[r * T + start: r * T + start + T] for r in past])
            ext = f.raw[past, s, start:start + T]
            hist = f.hist[past, start:start + T]
            for b in range(4):
                sl = slice(b * 36, (b + 1) * 36)
                delta = ext[:, sl] - hist[:, sl]
                den = float((delta * delta).sum())
                a = (float(np.clip((delta * (y[:, sl] - hist[:, sl])).sum() / den,
                                   0, alpha_hi)) if den > 1e-9 else 1.0)
                old = a * ext[:, sl] + (1 - a) * hist[:, sl]
                bias = (y[:, sl] - old).mean(0) * len(past) / (len(past) + shrink)
                dst = slice(start + b * 36, start + (b + 1) * 36)
                out[dst] = a * f.raw[d, s, dst] + (1 - a) * f.hist[d, dst] + bias
            f.fused[d, s] = np.maximum(out, 0)


def run(label, window=56, **kw):
    q3_forecast.WINDOW = window
    f = q3_forecast.Forecaster(q3_data.load_data())
    if kw:
        rebuild(f, **kw)
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    res = {}
    res["基线"] = run("基线 W=56")
    res["W84"] = run("W=84", window=84)
    res["W84_opt"] = run("W=84 + s28 + α≤1.25", window=84,
                         shrink=28, alpha_hi=1.25)
    res["W112_opt"] = run("W=112 + s28 + α≤1.25", window=112,
                          shrink=28, alpha_hi=1.25)
    (HERE / "_opt_final.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    b = res["基线"]["total_cost_yuan"]
    print()
    print("=== 最终对比 ===")
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<16}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-b)/1e4:+6.2f} 万")
