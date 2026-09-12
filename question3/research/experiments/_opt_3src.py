"""三源融合 + 同伴 LP：把 1401→13xx。

第三源 B = **上一期发布**
  · stage 0（0:00）：前一日 18:00 的发布（覆盖今日 0:00-18:00）
  · stage s>0     ：当期之前那一次发布（覆盖 [36s, 36s+108) ⊇ 剩余全天）
同伴只用 A(当期发布) + H(历史统计)，丢掉了 B。

拟合：逐 (stage, 6h子块) 做**因果**最小二乘  y ≈ c_A·A + c_H·H + c_B·B + c0
      训练样本仅取 d−56 … d−2（保证跨午夜未来已实现，无前视）。
融合：fused[d,s] = ā·A + ĥ·H + b̂·B + ĉ0，裁剪到 ≥0，超出 24h 的次日部分用 A/H 兜底。
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


def build_B(f):
    """第三源：上一期发布（对齐到当期 288 帧坐标系）。

    注意 raw[dj, sj] 的预报值存放在**索引 sj*36 起**（因为发布时刻为 sj*6 时），
    因此必须做偏移校正，否则错位。
    """
    T = 144
    N = len(f.data['pv'])
    # 各期发布的绝对起点与有效数组
    abs_axis = {}
    for d in range(N):
        for s in range(4):
            abs_axis[(d, s)] = (d * T + s * 36, f.raw[d, s, s * 36: s * 36 + T])
    B = np.full((N, 4, 2 * T), np.nan)
    for d in range(N):
        for s in range(4):
            idx = d * 4 + s - 1                      # 上一期
            if idx < 0:
                continue
            dj, sj = divmod(idx, 4)
            st0, arr = abs_axis[(dj, sj)]
            w0 = d * T + s * 36
            for off in range(2 * T):
                j = (w0 + off) - st0
                if 0 <= j < T:
                    B[d, s, off] = arr[j]
    return B


def build_fused3(f, B, use_B=True, sub=36, ridge=0.0, clip_coef=False):
    """返回三源融合数组 (N,4,288)。"""
    N = len(f.data['pv'])
    flat = f.data['pv'].ravel()
    out = f.fused.copy()
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
            B_all = B[past, s, start:start + T]
            for b in range(4):
                sl = slice(b * sub, (b + 1) * sub)
                y = y_all[:, sl].ravel()
                A_ = A_all[:, sl].ravel()
                H_ = H_all[:, sl].ravel()
                B_ = B_all[:, sl].ravel()
                m = np.isfinite(A_) & np.isfinite(H_) & np.isfinite(B_) & np.isfinite(y)
                if use_B and m.sum() >= 30:
                    X = np.c_[A_[m], H_[m], B_[m], np.ones(m.sum())]
                else:
                    m2 = np.isfinite(A_) & np.isfinite(H_) & np.isfinite(y)
                    if m2.sum() < 30:
                        continue
                    X = np.c_[A_[m2], H_[m2], np.ones(m2.sum())]
                    y = y[m2]
                yv = y[m] if (use_B and m.sum() >= 30) else y
                coef, *_ = np.linalg.lstsq(X, yv, rcond=None)
                if clip_coef:
                    coef[:-1] = np.clip(coef[:-1], 0, 1)
                # 应用到当期
                a = np.nan_to_num(f.raw[d, s, start + b * sub: start + (b + 1) * sub])
                h = f.hist[d, start + b * sub: start + (b + 1) * sub]
                if X.shape[1] == 4:
                    bb = np.nan_to_num(B[d, s, start + b * sub: start + (b + 1) * sub])
                    val = coef[0] * a + coef[1] * h + coef[2] * bb + coef[3]
                else:
                    val = coef[0] * a + coef[1] * h + coef[2]
                pred[start + b * sub: start + (b + 1) * sub] = val
            out[d, s] = np.maximum(pred, 0)
    return out


def run(label, **kw):
    f = q3_forecast.Forecaster(q3_data.load_data())
    B = build_B(f)
    if kw.pop('use_B', True):
        f.fused = build_fused3(f, B, **kw)
    else:
        f.fused = build_fused3(f, B, use_B=False, **kw)
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    res = {}
    res["2源(复现同伴)"] = run("2源", use_B=False)
    res["3源"] = run("3源")
    res["3源+α裁剪"] = run("3源+α裁剪", clip_coef=True)
    (HERE / "_opt_3src.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    b = res["2源(复现同伴)"]["total_cost_yuan"]
    print()
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<16}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-b)/1e4:+6.2f}")
