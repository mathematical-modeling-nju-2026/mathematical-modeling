"""在同伴预报基础上寻找更优的光伏预报构造（统一用加权 MAE 评估）。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from q3_data import load_actual, load_forecast, T, STAGE_HOUR

P = np.load(HERE / "_peer_fc.npz")
PV = P["pv"]; hist288 = P["hist"]; raw = P["raw"]; fused_peer = P["fused"]
L, PV_ = load_actual()
FC, _ = load_forecast()
COV = {0: 144, 1: 108, 2: 72, 3: 36}


def wmae(get):
    s = 0.0
    for k in range(4):
        a, b = k * 36, min(k * 36 + T, T)
        e = [np.abs(get(d, k, a, b) - PV[d, a:b]) for d in range(31, 365)]
        s += COV[k] * np.concatenate(e).mean()
    return s / sum(COV.values())


def eval_fused(FUSED):
    return wmae(lambda d, s, a, b: FUSED[d, s, a:b])


print("基准：")
print(f"  同伴 fused              {eval_fused(fused_peer):7.2f} kW")
print(f"  同伴 raw（附件3展开）    {wmae(lambda d,s,a,b: raw[d,s,a:b]):7.2f} kW")

# 统计基预测（2天视野，与同伴 hist 同构：今天+明天）
def stat2(d, s):
    """带漂移校正的统计预测（今天+明天各 144 段），仅用 d 之前的历史。"""
    a, b = STAGE_HOUR[s] * 6, STAGE_HOUR[s] * 6 + T
    def kernel(j):
        ix = [j - 7 * q for q in range(1, 5) if 0 <= j - 7 * q < j]
        return PV_[ix].mean(0) if ix else None
    def kernel_daily(j):
        return PV_[max(0, j - 7):j].mean(0) if j > 0 else None
    out = np.zeros(T)
    for (src_j, off) in ((d, 0), (d + 1, 0)):
        pass
    # 简化：用 7 日均值 + 28 日漂移，构造 [a,b) 段
    tgt = np.arange(a, b)
    vals = np.zeros(len(tgt))
    for i, t in enumerate(tgt):
        j = d + t // T
        if j >= len(PV_):
            j = len(PV_) - 1
        tt = t % T
        rawv = PV_[max(0, j - 7):j, tt].mean() if j > 0 else 0.0
        errs = [PV_[q, tt] - (PV_[max(0, q - 7):q, tt].mean() if q > 0 else 0.0)
                for q in range(max(0, j - 28), j)]
        vals[i] = rawv + (np.mean(errs) if errs else 0.0)
    return np.maximum(vals, 0)


# 候选 1：同伴 raw 与 同伴 hist 的「重新拟合」——分块 α + 截距 + 可选未截断 + 时新加权
def build(sub=36, intercept=False, clip=True, tau=None, use_hist288=True):
    out = np.zeros_like(raw)
    n_d = len(PV)
    for s in range(4):
        base = STAGE_HOUR[s] * 6
        for b in range(4):
            a0, a1 = base + b * sub, min(base + (b + 1) * sub, T)
            if a0 >= T:
                break
            idx = np.arange(a0, a1)
            for d in range(n_d):
                if np.isnan(raw[d, s, idx]).any():
                    out[d, s, idx] = np.nan_to_num(raw[d, s, idx])
                    continue
                past = [j for j in range(max(0, d - 56), max(0, d - 1))
                        if not np.isnan(raw[j, s, idx]).any()]
                if len(past) < 7:
                    out[d, s, idx] = np.maximum(raw[d, s, idx], 0)
                    continue
                pa = np.array(past)
                F = np.array([raw[j, s, idx] for j in past])
                H = hist288[pa][:, idx]
                V = PV[pa][:, idx]
                w = None if tau is None else np.exp(-(d - pa) / tau)[:, None]
                dlt = (F - H).ravel()
                y = (V - H).ravel()
                if w is not None:
                    ww = np.repeat(w, len(idx))
                    A = np.c_[dlt, np.ones_like(dlt)] if intercept else dlt[:, None]
                    Aw = A * np.sqrt(ww)[:, None]; yw = y * np.sqrt(ww)
                    coef, *_ = np.linalg.lstsq(Aw, yw, rcond=None)
                else:
                    A = np.c_[dlt, np.ones_like(dlt)] if intercept else dlt[:, None]
                    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
                al = coef[0]
                if clip:
                    al = float(np.clip(al, 0, 1))
                b0 = coef[1] if intercept else 0.0
                out[d, s, idx] = np.maximum(al * raw[d, s, idx]
                                            + (1 - al) * hist288[d, idx] + b0, 0)
    return out


print()
print("候选（α 拟合变体）:")
cfgs = [
    ("peer式(α裁剪,无截距,均权,6h块)", dict(sub=36, intercept=False, clip=True, tau=None)),
    ("+截距", dict(sub=36, intercept=True, clip=True, tau=None)),
    ("+时新加权τ=14", dict(sub=36, intercept=False, clip=True, tau=14)),
    ("+截距+时新加权", dict(sub=36, intercept=True, clip=True, tau=14)),
    ("1h块", dict(sub=6, intercept=False, clip=True, tau=None)),
    ("1h块+截距", dict(sub=6, intercept=True, clip=True, tau=None)),
    ("1h块+截距+时新", dict(sub=6, intercept=True, clip=True, tau=14)),
]
best = None
for nm, kw in cfgs:
    F = build(**kw)
    m = eval_fused(F)
    print(f"  {nm:<34}{m:7.2f} kW", flush=True)
    if best is None or m < best[0]:
        best = (m, nm, kw, F)
print(f"\n最优: {best[1]}  {best[0]:.2f} kW  (同伴 103.09)")
np.savez_compressed(HERE / "_opt_fused.npz", fused=best[3], name=best[1])
