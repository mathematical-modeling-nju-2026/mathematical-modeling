"""多源融合扩展：A(当期) + H(历史) + B1(上一期) + B2(前两期) + ... 

原理：每次发布都覆盖未来 24h，因此决策时刻可用的发布集合为
  stage 0（0:00）：前一日 18:00 / 12:00 / 6:00 / 0:00（均覆盖今日部分时段）
  stage s>0     ：当日 (s-1) / (s-2) / ... 的发布
所有这些都是**合法可得**的信息，同伴只用了当期发布。
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
W_FIT, FIRST_R = 56, 7


def build_lag_sources(f, max_lag=3):
    """lag 源：k 期之前的发布，映射到**绝对时间轴**再取当期窗口。

    绝对时间轴（10min 索引）：abs = day*144 + slot。
    第 (d,s) 期发布的绝对起点 = d*144 + s*36，覆盖 abs ∈ [start, start+144)。
    要取"当期窗口 [d*144 + s*36, +288)"（含次日）中，由 lag k 期发布给出的值。
    """
    N = len(f.data['pv'])
    # 每期发布的绝对起点与预报数组（注意 raw[dj,sj] 的预报存放在索引 sj*36 起）
    abs_src = {}
    for d in range(N):
        for s in range(4):
            st0 = d * T + s * 36
            arr = f.raw[d, s, s * 36: s * 36 + T]
            abs_src[(d, s)] = (st0, arr)
    srcs = {}
    for k in range(1, max_lag + 1):
        S = np.full((N, 4, 2 * T), np.nan)
        for d in range(N):
            for s in range(4):
                idx = d * 4 + s - k
                if idx < 0:
                    continue
                dj, sj = divmod(idx, 4)
                st0, arr = abs_src[(dj, sj)]
                w0 = d * T + s * 36
                for off in range(2 * T):
                    j = (w0 + off) - st0
                    if 0 <= j < T:
                        S[d, s, off] = arr[j]
        srcs[k] = S
    return srcs


def build_fused_multi(f, srcs, n_src=1, sub=36, clip_coef=False):
    """n_src=0: A+H；1: +lag1；2: +lag1,lag2；..."""
    N = len(f.data['pv'])
    flat = f.data['pv'].ravel()
    out = f.fused.copy()
    lags = list(range(1, n_src + 1))
    for s in range(4):
        start = s * 36
        for d in range(N):
            pred = f.raw[d, s].copy()
            past = np.arange(max(FIRST_R, d - W_FIT), max(FIRST_R, d - 1))
            if len(past) < 7:
                out[d, s] = np.maximum(pred, 0); continue
            y_all = np.array([flat[r * T + start: r * T + start + T] for r in past])
            A_all = f.raw[past, s, start:start + T]
            H_all = f.hist[past, start:start + T]
            L_all = [srcs[k][past, s, start:start + T] for k in lags]
            for b in range(4):
                sl = slice(b * sub, (b + 1) * sub)
                y = y_all[:, sl].ravel()
                cols = [A_all[:, sl].ravel(), H_all[:, sl].ravel()]
                cols += [L[:, sl].ravel() for L in L_all]
                m = np.isfinite(y)
                for c in cols:
                    m &= np.isfinite(c)
                if m.sum() < 30:
                    continue
                X = np.c_[*[c[m] for c in cols], np.ones(m.sum())]
                coef, *_ = np.linalg.lstsq(X, y[m], rcond=None)
                if clip_coef:
                    coef[:-1] = np.clip(coef[:-1], 0, 1)
                cur = [np.nan_to_num(f.raw[d, s, start + b * sub: start + (b + 1) * sub]),
                       f.hist[d, start + b * sub: start + (b + 1) * sub]]
                cur += [np.nan_to_num(srcs[k][d, s,
                                              start + b * sub: start + (b + 1) * sub])
                        for k in lags]
                val = coef[-1]
                for c, cc in zip(cur, coef[:-1]):
                    val = val + cc * c
                pred[start + b * sub: start + (b + 1) * sub] = val
            out[d, s] = np.maximum(pred, 0)
    return out


def run(label, n_src=1, **kw):
    f = q3_forecast.Forecaster(q3_data.load_data())
    srcs = build_lag_sources(f, max_lag=3)
    f.fused = build_fused_multi(f, srcs, n_src=n_src, **kw)
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    res = {}
    res["A+H"] = run("A+H", 0)
    res["+B1"] = run("+B1", 1)
    res["+B1B2"] = run("+B1+B2", 2)
    res["+B1B2B3"] = run("+B1+B2+B3", 3)
    (HERE / "_opt_multi2.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    b = res["A+H"]["total_cost_yuan"]
    print()
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<12}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-b)/1e4:+6.2f}")
