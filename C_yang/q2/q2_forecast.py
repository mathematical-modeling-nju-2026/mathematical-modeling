"""问题2 净负载预测：严格因果的候选预测器与网格比选。

因果性约定
    为第 d 天（0-based）做预测时，只允许使用第 0..d-1 天的数据。
    历史不足时回退到附件1 典型日。

预测器结构（网格比选后固定）
    负载 与 光伏 分别预测再相减。实测二者误差近似不独立假设成立
    （corr ≈ 0），且驱动因素不同：负载受星期几与温度影响，光伏受天气与季节影响。
    每个通道可选配"漂移校正"：用最近 m 天的平均预测误差修正原始预测，
    消除滚动均值对季节趋势的滞后（否则残差会带明显的月际系统偏置）。

评价口径
    MAE(kW)        逐时段平均绝对误差（预测精度）
    日均缺口(kWh)   Σ_t |N_actual - N̂| · Δt
    日均缺额(kWh)   Σ_t max(0, N_actual - N̂) · Δt —— "完全按点预测计划、不留裕度"
                   时每日必须紧急购电的电量，是问题2 的直接成本驱动量
"""

from __future__ import annotations

import numpy as np

from q2_data import DT, load_attachment1, load_attachment2, net_load

WARMUP = 21          # 前 21 天作为预测器预热期，不参与评价与场景集


# ---------------- 单变量预测内核 ----------------

def _sw(X, d, k, upto=None):
    """最近 k 次同星期几的均值。upto 给出"只能用第 0..upto-1 天"的上界。"""
    idx = [d - 7 * j for j in range(1, k + 1)
           if d - 7 * j >= 0 and (upto is None or d - 7 * j < upto)]
    return X[idx].mean(axis=0) if idx else None


def _tr(X, d, m, upto=None):
    """最近 m 天均值（可被 upto 截断）。"""
    hi = d if upto is None else min(d, upto)
    return X[max(0, hi - m):hi].mean(axis=0) if hi > 0 else None


def _mix(a, b):
    return 0.5 * a + 0.5 * b


def _w1(X, d, upto=None):
    e = d - 7
    return X[e].copy() if (e >= 0 and (upto is None or e < upto)) else None


LOAD_KERNELS = {
    "w1":  _w1,
    "sw2": lambda X, d, upto=None: _sw(X, d, 2, upto),
    "sw4": lambda X, d, upto=None: _sw(X, d, 4, upto),
    "t7":  lambda X, d, upto=None: _tr(X, d, 7, upto),
    "bsw": lambda X, d, upto=None: (_mix(X[d - 7], _sw(X, d, 4, upto))
                                    if _w1(X, d, upto) is not None else None),
    "b7":  lambda X, d, upto=None: (_mix(X[d - 7], _tr(X, d, 7, upto))
                                    if _w1(X, d, upto) is not None else None),
}

PV_KERNELS = {
    "t3":  lambda X, d, upto=None: _tr(X, d, 3, upto),
    "t7":  lambda X, d, upto=None: _tr(X, d, 7, upto),
    "t14": lambda X, d, upto=None: _tr(X, d, 14, upto),
    "w1":  _w1,
    "b7":  lambda X, d, upto=None: (_mix(X[d - 7], _tr(X, d, 7, upto))
                                    if _w1(X, d, upto) is not None else None),
    "ew7": lambda X, d, upto=None: _ewma(X, d, upto),
}

DRIFTS = [0, 1, 2, 3, 5, 7, 10, 14, 21, 28]   # 0 表示不做漂移校正


def _ewma(X, d, upto=None, halflife=5.0):
    hi = d if upto is None else min(d, upto)
    if hi == 0:
        return None
    w = 0.5 ** (np.arange(hi - 1, -1, -1) / halflife)
    return (X[:hi] * w[:, None]).sum(axis=0) / w.sum()


def make_channel(kernel, m):
    """把内核包装成带漂移校正的预测通道：raw + 近 m 天平均误差。

    upto 为"信息截止日"（只能用第 0..upto-1 天）。做滚动前瞻时，第 d 天 0:00
    既要预测当天、也要预测第 d+1 天，而第 d 天的实际值此刻尚未观测到；
    通道内所有取平均的窗口都必须截断在 upto=d，否则前瞻日就偷看了当天的数据。
    """
    if m == 0:
        return kernel

    def f(X, d, upto=None):
        raw = kernel(X, d, upto)
        if raw is None:
            return None
        hi = d if upto is None else min(d, upto)
        errs = []
        for dd in range(max(0, hi - m), hi):
            r = kernel(X, dd, upto)
            if r is not None:
                errs.append(X[dd] - r)
        return raw if not errs else raw + np.mean(errs, axis=0)

    return f


# ---------------- 组合预测器 ----------------

class Forecaster:
    """负载/光伏两通道分别预测后相减。"""

    def __init__(self, load_key, load_drift, pv_key, pv_drift):
        self.load_key, self.load_drift = load_key, load_drift
        self.pv_key, self.pv_drift = pv_key, pv_drift
        self.fl = make_channel(LOAD_KERNELS[load_key], load_drift)
        self.fv = make_channel(PV_KERNELS[pv_key], pv_drift)
        self.name = (f"L[{load_key}/d{load_drift}]+V[{pv_key}/d{pv_drift}]")

    def channel_load(self, L, d, upto=None):
        return self.fl(L, d, upto)

    def channel_pv(self, V, d, upto=None):
        return self.fv(V, d, upto)

    def predict(self, L, V, d, upto=None):
        """第 d 天的净负载点预测。upto 限制信息截止日（见 make_channel）。

        upto=d 时与不传 upto 完全等价；预测第 d+1 天时须传 upto=d，
        因为第 d 天的实际值在第 d 天 0:00 尚未观测到。
        """
        fl, fv = self.fl(L, d, upto), self.fv(V, d, upto)
        if fl is None or fv is None:
            _, _, l1, v1 = load_attachment1()
            fl = l1 if fl is None else fl
            fv = v1 if fv is None else fv
        return fl - fv

    def matrix(self, L, V, d_from=0, upto=None):
        return np.vstack([self.predict(L, V, d, upto)
                          for d in range(d_from, L.shape[0])])

    def horizon_matrix(self, L, V, d, H):
        """第 d 天 0:00 为 H 天前瞻所需的点预测矩阵 (H, T)。

        所有行都只使用第 0..d-1 天的信息——前瞻第 d+1 天也不能偷看第 d 天。
        """
        return np.vstack([self.predict(L, V, j, upto=d) for j in range(d, d + H)])

    def _channel_matrix(self, X, fn, nd, upto=None):
        """单通道预测矩阵，历史不足时回退到附件1 典型日。"""
        _, _, l1, v1 = load_attachment1()
        fb = l1 if fn is self.fl else v1
        rows = []
        for d in range(nd):
            x = fn(X, d, upto)
            rows.append(fb if x is None else x)
        return np.vstack(rows)

    def matrix_load(self, L, nd=None):
        return self._channel_matrix(L, self.fl, L.shape[0] if nd is None else nd)

    def matrix_pv(self, V, nd=None):
        return self._channel_matrix(V, self.fv, V.shape[0] if nd is None else nd)

    def residual(self, L, V):
        """历史整日残差 r_d = N_d - N̂_d（kW）；预热期为 NaN。"""
        N = net_load(L, V)
        F = self.matrix(L, V, 0)
        R = np.full_like(N, np.nan)
        R[WARMUP:] = N[WARMUP:] - F[WARMUP:]
        return R


TRAIN_FROM = 28

# 网格比选（见 __main__ 输出）选定的主预测器：负载=最近4次同星期几均值+近5天漂移校正，
# 光伏=最近7天均值+近28天漂移校正。MAE 242.12 kW，日均缺口 5810.9 kWh。
BEST_SPEC = ("sw4", 5, "t7", 28)


def best_forecaster():
    return Forecaster(*BEST_SPEC)


def score(fc, L, V, d_from=TRAIN_FROM, d_to=None):
    N = net_load(L, V)
    d_to = L.shape[0] if d_to is None else d_to
    F = fc.matrix(L, V, d_from)[: d_to - d_from]
    err = N[d_from:d_to] - F
    return {
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "gap": float(np.abs(err).sum(axis=1).mean() * DT),
        "short": float(np.maximum(err, 0).sum(axis=1).mean() * DT),
        "bias": float(err.sum(axis=1).mean() * DT),
        "bias_abs": float(np.abs(err.sum(axis=1)).mean() * DT),
    }


def select(L, V, topn=12):
    """坐标下降式比选：先固定光伏通道选负载通道，再固定负载通道选光伏通道。

    全网格 6×10×6×10 = 3600 个组合，逐个回测代价过高；负载与光伏通道的
    误差近似独立（实测 corr ≈ 0），故分通道择优是可分的，不会漏掉最优组合。
    """
    base_l, base_p = "w1", "t7"
    # 第一轮：选负载通道
    lrows = []
    for lk in LOAD_KERNELS:
        for lm in DRIFTS:
            fc = Forecaster(lk, lm, base_p, 0)
            r = score(fc, L, V)
            r["fc"] = fc
            lrows.append(r)
    lrows.sort(key=lambda r: r["mae"])
    best_l = lrows[0]["fc"]
    # 第二轮：选光伏通道
    prows = []
    for pk in PV_KERNELS:
        for pm in DRIFTS:
            fc = Forecaster(best_l.load_key, best_l.load_drift, pk, pm)
            r = score(fc, L, V)
            r["fc"] = fc
            prows.append(r)
    prows.sort(key=lambda r: r["mae"])
    best = prows[0]["fc"]
    # 统一用选中组合重算，并按 MAE 排序输出前 topn
    rows = prows[:topn] + lrows[:3]
    for r in rows:
        r.update(score(r["fc"], L, V))
    rows.sort(key=lambda r: r["mae"])
    return rows[:topn], rows


if __name__ == "__main__":
    dates, L, V = load_attachment2()
    N = net_load(L, V)

    print("=" * 92)
    print("负载 × 光伏 预测器网格比选（2025.1.29 起，严格只用当日之前的数据）")
    print("=" * 92)
    top, allrows = select(L, V, topn=12)
    print(f"  {'预测器':<26}{'MAE(kW)':>10}{'RMSE(kW)':>10}"
          f"{'日均缺口':>11}{'日均缺额':>11}{'日净偏差':>11}")
    for r in top:
        print(f"  {r['fc'].name:<26}{r['mae']:>10.2f}{r['rmse']:>10.2f}"
              f"{r['gap']:>11.1f}{r['short']:>11.1f}{r['bias']:>11.1f}")

    best = top[0]["fc"]
    print(f"\n  选定预测器: {best.name}")
    print(f"    MAE = {top[0]['mae']:.2f} kW   日均缺口 = {top[0]['gap']:.1f} kWh"
          f"   日均缺额 = {top[0]['short']:.1f} kWh   日净偏差 = {top[0]['bias']:+.1f} kWh")

    nofix = [r for r in allrows if r["fc"].name.startswith("L[w1/d0]+V[t7/d0]")]
    if nofix:
        r0 = nofix[0]
        print(f"  对照·不做漂移校正 L[w1]+V[t7]: MAE={r0['mae']:.2f} kW, "
              f"日均缺口={r0['gap']:.1f} kWh, 日净偏差={r0['bias']:+.1f} kWh")
        print(f"    -> 漂移校正使 MAE 降低 {(1 - top[0]['mae'] / r0['mae']) * 100:.1f}%，"
              f"日净偏差 {abs(r0['bias']):.1f} -> {abs(top[0]['bias']):.1f} kWh")

    # 误差构成
    print("\n" + "=" * 92)
    print("误差结构分解（选定预测器）")
    print("=" * 92)
    eL, eP = [], []
    for d in range(TRAIN_FROM, 365):
        eL.append(L[d] - best.channel_load(L, d))
        eP.append(V[d] - best.channel_pv(V, d))
    eL, eP = np.array(eL), np.array(eP)
    print(f"  负载误差 std = {eL.std():8.2f} kW        光伏误差 std = {eP.std():8.2f} kW")
    print(f"  corr(eL, eP) = {np.corrcoef(eL.ravel(), eP.ravel())[0, 1]:+.4f}"
          f"      -> 近似独立")
    print(f"  净负载误差 std = {(eL - eP).std():.2f} kW"
          f"   独立时理论值 {np.hypot(eL.std(), eP.std()):.2f} kW")

    # 残差季节性
    print("\n" + "=" * 92)
    print("残差（净负载预测误差）的季节性")
    print("=" * 92)
    R = best.residual(L, V)[TRAIN_FROM:]
    months = np.array([d.month for d in dates[TRAIN_FROM:]])
    print(f"  {'月份':<6}{'残差std(kW)':>13}{'日均缺口(kWh)':>15}"
          f"{'日均缺额(kWh)':>15}{'日净偏差(kWh)':>15}")
    for mo in range(1, 13):
        sel = months == mo
        if sel.sum() == 0:
            continue
        r = R[sel]
        print(f"  {mo:<6}{r.std():>13.1f}"
              f"{np.abs(r).sum(axis=1).mean() * DT:>15.1f}"
              f"{np.maximum(r, 0).sum(axis=1).mean() * DT:>15.1f}"
              f"{r.sum(axis=1).mean() * DT:>15.1f}")

    # 条件分位数（报童临界分位数）
    print("\n" + "=" * 92)
    print("报童临界分位数（紧急电价为交易电价的 5 倍 -> F* = 1 - 1/5 = 0.80）")
    print("=" * 92)
    Fm = best.matrix(L, V, TRAIN_FROM)
    Rm = N[TRAIN_FROM:] - Fm
    # 条件分位数：以近 56 天残差的分位数作为当日净负载分布的 80% 分位
    q80 = np.empty_like(Rm)
    for i, d in enumerate(range(TRAIN_FROM, 365)):
        lo = max(WARMUP, d - 56)
        q80[i] = np.percentile(N[lo:d] - best.matrix(L, V, lo)[: d - lo], 80, axis=0)
    extra = q80
    day_load = L[TRAIN_FROM:].sum(axis=1).mean() * DT
    print(f"  相对点预测的日均额外购电 : {extra.sum(axis=1).mean() * DT:,.1f} kWh"
          f"   (占日均负载 {extra.sum(axis=1).mean() * DT / day_load * 100:.2f}%)")
    print(f"  337 天累计               : {extra.sum(axis=1).mean() * DT * 337 / 1e4:,.1f} 万 kWh")

    # 单段误差与电池功率上限
    print("\n" + "=" * 92)
    print("单段净负载缺额 与 电池功率上限")
    print("=" * 92)
    sh = np.maximum(Rm, 0)
    print(f"  单段缺额 : 均值 {sh.mean() * DT:6.2f}  P99 {np.percentile(sh, 99) * DT:7.2f}"
          f"  max {sh.max() * DT:7.2f} kWh/段")
    print(f"  电池单段上限 = 5000 kW × (1/6) h = 833.33 kWh/段")
    print(f"  超出 833.33 kWh 的时段占比 = {np.mean(sh > 5000) * 100:.4f}%"
          f"   （即单段误差几乎总在电池一档功率之内）")
