"""诊断：多预报源融合（当期发布 + 上一期发布 + 历史统计）。

洞察
  同伴只融合 H(历史统计) + A(当期发布)，丢弃了 **B(上一期发布)**。
  但 B 是合法可得且独立的信息：
    · stage 0（0:00）：上一期 = 前一日 18:00 发布，覆盖今日 0:00-18:00
    · stage s>0     ：上一期 = 当日 (s-1)*6 时发布，覆盖 [s*36, s*36+108)
  关键：**首个 6 小时决策窗（最影响成本）B 始终可用**。

本脚本仅评估 MAE（不跑 LP），快速判断方向是否值得投入。
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE / "_peer_lab"
sys.path.insert(0, str(LAB))

import q3_data, q3_forecast          # noqa: E402

T = q3_data.T
f = q3_forecast.Forecaster(q3_data.load_data())
PV = f.data['pv']
N = len(PV)
flat = PV.ravel()
W = 56          # 拟合窗口
FR = 7          # 首个可用残差日

# ---------- 构造上一期发布源 B（对齐到当期 origin 的 288 帧） ----------
B = np.full((N, 4, 2 * T), np.nan)
for d in range(N):
    for s in range(4):
        if s == 0:
            if d == 0:
                continue
            src = f.raw[d - 1, 3]
            B[d, s, 0:108] = src[144:252]      # 前一日 18:00 预报 → 今日 0:00-18:00
        else:
            src = f.raw[d, s - 1]
            lo = s * 36
            B[d, s, lo:lo + 108] = src[lo:lo + 108]

print("B 源可用性检查：")
for s in range(4):
    ok = np.isfinite(B[100, s, s * 36:s * 36 + 36]).all()
    print(f"  stage {s}: 首 6h 可用 = {ok}")

# ---------- 分类统计：2 源 vs 3 源 ----------
rows = []
for s in range(4):
    start = s * 36
    for b in range(4):
        lo, hi = start + b * 36, start + b * 36 + 36
        e2, e3, ep, eB = [], [], [], []
        for d in range(N):
            if d * T + hi > N * T:
                break
            y = flat[d * T + lo: d * T + hi]
            A_ = f.raw[d, s][lo:hi]
            H_ = f.hist[d][lo:hi]
            Bb = B[d, s][lo:hi]
            past = [r for r in range(max(FR, d - W), max(FR, d - 1))]
            if len(past) >= 7:
                Y = np.concatenate([flat[r * T + lo: r * T + hi] for r in past])
                Aa = np.concatenate([f.raw[r, s][lo:hi] for r in past])
                Hh = np.concatenate([f.hist[r][lo:hi] for r in past])
                Bp = np.concatenate([B[r, s][lo:hi] for r in past])
                m = np.isfinite(Aa) & np.isfinite(Hh) & np.isfinite(Bp) & np.isfinite(Y)
                if m.sum() >= 30:
                    X2 = np.c_[Aa[m], Hh[m], np.ones(m.sum())]
                    c2, *_ = np.linalg.lstsq(X2, Y[m], rcond=None)
                    X3 = np.c_[Aa[m], Hh[m], Bp[m], np.ones(m.sum())]
                    c3, *_ = np.linalg.lstsq(X3, Y[m], rcond=None)
                else:
                    c2 = np.array([1., 0., 0.]); c3 = np.r_[c2, 0.]
            else:
                c2 = np.array([1., 0., 0.]); c3 = np.r_[c2, 0.]
            A0 = np.nan_to_num(A_); H0 = np.nan_to_num(H_)
            p2 = c2[0] * A0 + c2[1] * H0 + c2[2]
            p3 = (c3[0] * A0 + c3[1] * H0 + c3[2] * np.nan_to_num(Bb) + c3[3]
                  if np.isfinite(Bb).all() else p2)
            e2.append(np.abs(p2 - y)); e3.append(np.abs(p3 - y))
            eB.append(np.abs(np.nan_to_num(Bb) - y))
        if e2:
            rows.append((s, b, np.concatenate(e2).mean(),
                         np.concatenate(e3).mean(), np.concatenate(eB).mean()))

print()
print(f"{'stage':>6}{'块':>4}{'2源MAE':>10}{'3源MAE':>10}{'B单源MAE':>11}{'改善':>9}")
for s, b, m2, m3, mb in rows:
    print(f"{s*6:>4}时{b:>4}{m2:>10.2f}{m3:>10.2f}{mb:>11.2f}{m2-m3:>+9.2f}")

# 加权（首块权重高）
w = {(s, b): v for s in range(4)
     for b, v in ((0, 0.5), (1, 0.2), (2, 0.15), (3, 0.15))}
num2 = num3 = den = 0.0
for s, b, m2, m3, mb in rows:
    num2 += w[(s, b)] * m2; num3 += w[(s, b)] * m3; den += w[(s, b)]
print()
print(f"加权 MAE（首块权重 0.5）：2源 {num2/den:.2f} → 3源 {num3/den:.2f}  "
      f"改善 {num2/den - num3/den:+.2f} kW")
