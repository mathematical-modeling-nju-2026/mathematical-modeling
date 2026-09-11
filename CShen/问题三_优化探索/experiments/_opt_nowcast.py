"""诊断：预报偏差对成本的贡献。

思路
  同伴的融合 = α·A + (1−α)·H + bias，其中 bias 是「历史平均残差」。
  但**当天**发布的预报如果有系统性偏差（例如整体高估/低估），
  bias 用的是 56 天窗口，可能不足以反映**当期**偏差水平。

实验
  · debias_now: 用「最近 n 天、同一发布时刻」的**当期级偏差**替代/叠加原 bias
  · 检验不同 n（3/7/14/28）下的总费用
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


def add_nowcast_bias(f, n_days=7, weight=1.0, sub=36):
    """在同伴 fused 基础上，叠加「近 n_days 天同发布时刻」的当期偏差校正。"""
    flat = f.data['pv'].ravel()
    N = len(f.data['load'])
    fused = f.fused.copy()
    for s in range(4):
        start = s * 36
        for d in range(N):
            past = [r for r in range(max(7, d - n_days), max(7, d - 1))]
            if len(past) < 2:
                continue
            corr = np.zeros(T)
            cnt = np.zeros(T)
            for r in past:
                y = flat[r * T + start: r * T + start + T]
                pred = f.fused[r, s, start:start + T]
                dev = y - pred
                m = np.isfinite(dev)
                corr[m] += dev[m]
                cnt[m] += 1
            with np.errstate(invalid='ignore'):
                avg = np.where(cnt > 0, corr / np.maximum(cnt, 1), 0.0)
            # 分块平滑（避免逐帧噪声）
            for b in range(4):
                sl = slice(b * sub, (b + 1) * sub)
                if cnt[sl].sum() > 0:
                    avg[sl] = avg[sl].mean()
            fused[d, s, start:start + T] = np.maximum(
                fused[d, s, start:start + T] + weight * avg, 0)
    return fused


def run(label, **kw):
    f = q3_forecast.Forecaster(q3_data.load_data())
    if kw:
        f.fused = add_nowcast_bias(f, **kw)
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    res = {}
    res["基线"] = run("基线")
    for n in (3, 7, 14):
        res[f"当期偏差n={n}"] = run(f"当期偏差 n={n}", n_days=n, weight=1.0)
    res["当期偏差n=7,w=0.5"] = run("n=7, w=0.5", n_days=7, weight=0.5)
    (HERE / "_opt_nowcast.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    b = res["基线"]["total_cost_yuan"]
    print()
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<22}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-b)/1e4:+6.2f}")
