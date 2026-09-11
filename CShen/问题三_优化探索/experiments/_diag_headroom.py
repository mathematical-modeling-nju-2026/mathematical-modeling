"""关键诊断：预报侧是否还有提升空间？

测三件事
  1. 当前融合的 MAE vs **样本内最优权重**的 MAE（上界）—— 判断权重是否已饱和
  2. **分月/分季**的 MAE 与偏差 —— 找是否有系统性时期问题
  3. 净负载误差的**负载部分 / 光伏部分**分解 —— 找准优化重点
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "_peer_lab"))

import q3_data, q3_forecast            # noqa: E402

T = 144
f = q3_forecast.Forecaster(q3_data.load_data())
PV = f.data['pv']; L = f.data['load']
flat = PV.ravel()
N = len(PV)
FIRST_R, WFIT = 7, 56

# ---------- 1. 当前融合 vs 样本内最优（oracle） ----------
rows = []
for s in range(4):
    start = s * 36
    for b in range(4):
        lo, hi = start + b * 36, start + b * 36 + 36
        if hi > T:
            continue
        e_cur, e_ext, e_hist = [], [], []
        for d in range(31, N):
            y = flat[d * T + lo: d * T + hi]
            if y.size < 36:
                break
            cur = f.fused[d, s][lo:hi]
            A_ = f.raw[d, s][lo:hi]
            H_ = f.hist[d][lo:hi]
            e_cur.append(np.abs(cur - y))
            e_ext.append(np.abs(A_ - y))
            e_hist.append(np.abs(H_ - y))
        m_cur = np.concatenate(e_cur).mean()
        m_ext = np.concatenate(e_ext).mean()
        m_his = np.concatenate(e_hist).mean()
        Y, Aa, Hh = [], [], []
        for d in range(31, N):
            yy = flat[d * T + lo: d * T + hi]
            if yy.size < 36:
                break
            Y.append(yy); Aa.append(f.raw[d, s][lo:hi]); Hh.append(f.hist[d][lo:hi])
        Y = np.concatenate(Y); Aa = np.concatenate(Aa); Hh = np.concatenate(Hh)
        X = np.c_[Aa, Hh, np.ones_like(Y)]
        coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
        orc = np.abs(X @ coef - Y).mean()
        rows.append((s, b, m_cur, orc, m_ext, m_his))

print("当前融合 vs 样本内最优(oracle) MAE：")
print(f"{'stage':>6}{'块':>4}{'当前':>10}{'oracle':>10}{'附件3':>10}{'历史':>10}{'余量':>9}")
w = {(s, b): v for s in range(4) for b, v in ((0, .5), (1, .2), (2, .15), (3, .15))}
nc = no = ne = nh = den = 0.0
for s, b, mc, mo, me, mh in rows:
    print(f"{s*6:>4}时{b:>4}{mc:>10.1f}{mo:>10.1f}{me:>10.1f}{mh:>10.1f}{mc-mo:>+9.1f}")
    k = w[(s, b)]; nc += k*mc; no += k*mo; ne += k*me; nh += k*mh; den += k
print(f"\n加权：当前 {nc/den:.2f}  oracle {no/den:.2f}  "
      f"附件3 {ne/den:.2f}  历史 {nh/den:.2f}")
print(f"→ 权重优化余量（下界估计） = {(nc-no)/den:.2f} kW")

# ---------- 2. 分月 MAE ----------
print()
print("分月 MAE（融合预报，加权，仅统计当天覆盖段）：")
for m0, m1, nm in [(31, 59, "2月"), (59, 90, "3月"), (90, 120, "4月"),
                   (120, 151, "5月"), (151, 181, "6月"), (181, 212, "7月"),
                   (212, 243, "8月"), (243, 273, "9月"), (273, 304, "10月"),
                   (304, 334, "11月"), (334, 365, "12月")]:
    ac, cnt = 0.0, 0
    for s in range(4):
        start = s * 36
        n_ok = T - start
        e = []
        for d in range(m0, min(m1, N)):
            y = flat[d * T + start: d * T + start + n_ok]
            if y.size < n_ok:
                continue
            e.append(np.abs(f.fused[d, s][start:start + n_ok] - y))
        if e:
            ac += np.concatenate(e).mean(); cnt += 1
    print(f"  {nm}: {ac/max(cnt,1):7.1f} kW")

# ---------- 3. 净负载误差分解 ----------
print()
print("净负载点预测误差分解（加权 MAE）：")
def net_mae(fn, name):
    tot = 0.0
    for s in range(4):
        start = s * 36
        e = []
        for d in range(31, N):
            pred = fn(d, s)
            act = (L[d] - PV[d])[start:start + T]
            e.append(np.abs(pred - act))
        tot += np.concatenate(e).mean()
    print(f"  {name:<28}{tot/4:8.2f} kW")

net_mae(lambda d, s: (L[d] - f.hist[d])[s*36:s*36+T] / 1
        if False else (L[d] - f.hist[d])[s*36:s*36+T], "纯历史（无融合）")
net_mae(lambda d, s: (L[d] - f.fused[d, s])[s*36:s*36+T], "融合（当前）")
