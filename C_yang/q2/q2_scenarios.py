"""问题2 场景集构造：历史整日残差向量 + 滚动窗口 + 场景削减。

为什么要"整日残差向量"而不是逐时段独立抽样
    逐时段抽样会破坏 144 个时段之间的相关结构（光伏误差在正午高度相关、
    负载误差有早晚高峰的持续段），会把"正午光伏偏高 + 傍晚负载偏高"这类
    真实存在的组合拆散，从而系统性低估风险、把计划压得过低。
    直接搬运历史上真实出现过的整日误差形态，天然保留了全部相关结构。

因果性
    为第 d 天构造场景集时，只使用 d 之前已经实现的历史残差
    （倒数窗口 [d-56, d-1]），且每个历史残差本身也是用当天之前的数据算出来的。

季节性
    残差 std 在 11 月约 229 kW、6 月约 491 kW，相差一倍以上。
    因此窗口取最近 56 天滚动，而不是全年混池——全年混池会把冬季的
    低波动错配到夏季。56 天也保证 8 个星期几各出现约 8 次。

年初样本偏薄
    附件2 只有 2025 一年，1 月 1 日起才开始积累历史，而预测器要到第 21 天
    才产出第一个有效残差。于是 2 月 1 日（报告期首日）窗口内只有约 10 条
    残差，要到 4 月中旬窗口才能填满 56 条。这是题目数据本身的限制：年初
    本来就"无史可依"，模型只能保守应对。本实现**不允许**用未来数据补足
    样本（见 window_residuals 的说明），只把场景数逐日列在报告里。

场景削减（可选）
    窗口 56 天即 56 个场景。决策日的随机规划只有 144 段、且场景只作用于决策日，
    56 个场景在计算上完全可承受，故默认**不做削减**：直接用窗口内全部历史残差
    并等权。这样做的好处是结果不依赖随机数——若改为重抽样配对，蒙特卡洛噪声
    会淹没前瞻长度这类小量对比（实测不同随机种子间差异可达 0.6%）。
    仍保留 k-medoids 削减（层次聚类 + 中心点，权重取簇内占比）作为可选，
    用于场景数敏感性检验。
"""

from __future__ import annotations

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform

from q2_data import DT, T

WINDOW = 56          # 场景窗口长度（天）
MIN_SCEN = 21        # 提示阈值：窗口内场景数少于该值时报"样本偏薄"


def window_residuals(R, d, window=WINDOW):
    """取第 d 天之前最近 window 天的有效残差向量（R 中未预热的行为 NaN）。

    只允许返回第 d 天**之前**的数据。历史不足时宁可少用几个场景，也绝不能
    回退到"全历史可用残差"——那会把 d 之后的残差也拉进来，直接破坏非前瞻性。
    这一条由 q2_verify.check_causality 逐日把关。
    """
    lo = max(0, d - window)
    Rw = R[lo:d]
    if Rw.shape[0] == 0:
        return Rw
    ok = ~np.isnan(Rw).any(axis=1)
    return Rw[ok]


def reduce_scenarios(R, S, seed=0):
    """k-medoids 场景削减：返回 (reps (S',T), weights (S',))。"""
    n = R.shape[0]
    if n <= S:
        return R.copy(), np.full(n, 1.0 / n)
    D = squareform(pdist(R))
    Z = linkage(squareform(D), method="average")
    lab = fcluster(Z, S, criterion="maxclust")
    reps, w = [], []
    for c in np.unique(lab):
        idx = np.where(lab == c)[0]
        sub = D[np.ix_(idx, idx)]
        med = idx[int(sub.sum(axis=1).argmin())]
        reps.append(R[med])
        w.append(len(idx))
    w = np.asarray(w, dtype=float)
    return np.asarray(reps), w / w.sum()


def build_scenarios(R, d, fc_day, S=None, window=WINDOW, seed=0):
    """第 d 天的场景集。

    参数
        R      : 历史整日残差矩阵 (365, T)，单位 kW，预热期为 NaN
        d      : 目标日
        fc_day : 该日的净负载点预测 (T,)，单位 kW
        S      : 若给出则做 k-medoids 削减；默认 None，直接用整个窗口
    返回
        scen (n, T) 净负载场景（kW），w (n,) 权重

    默认不做削减，直接用窗口内全部历史残差并等权——窗口 56 天对滚动模型
    完全可承受，且结果不依赖随机数，便于复现与横向比较。
    """
    Rw = window_residuals(R, d, window)
    if Rw.shape[0] == 0:
        # 尚无任何可用历史残差（年初预热期）：退化为点预测，不做不确定性刻画
        return fc_day[None, :].copy(), np.array([1.0])
    if S is None or Rw.shape[0] <= S:
        reps = Rw
        w = np.full(Rw.shape[0], 1.0 / Rw.shape[0])
    else:
        reps, w = reduce_scenarios(Rw, S, seed=seed)
    return fc_day[None, :] + reps, w


def scenario_stats(scen, w, fc_day):
    """场景集的描述统计，用于论文与校验。"""
    mean = w @ scen
    p80 = np.percentile(scen, 80, axis=0)
    return {
        "mean_deviation_kWh": float((mean - fc_day).sum() * DT),
        "p80_above_fc_kWh": float((p80 - fc_day).sum() * DT),
        "spread_std_kW": float(np.sqrt(w @ (scen - mean) ** 2).mean()),
    }


if __name__ == "__main__":
    from q2_data import load_attachment2, net_load
    from q2_forecast import TRAIN_FROM, WARMUP, best_forecaster

    dates, L, V = load_attachment2()
    N = net_load(L, V)
    best = best_forecaster()
    R = best.residual(L, V)

    print("=" * 80)
    print("场景集构造示例")
    print("=" * 80)
    for dd in [60, 180, 300]:
        fc = best.predict(L, V, dd)
        scen, w = build_scenarios(R, dd, fc, S=30)
        st = scenario_stats(scen, w, fc)
        print(f"  第 {dates[dd].date()} 日  场景数 {scen.shape[0]}  "
              f"场景均值偏离点预测 {st['mean_deviation_kWh']:+8.1f} kWh  "
              f"80%分位高于点预测 {st['p80_above_fc_kWh']:8.1f} kWh")

    print("\n" + "=" * 80)
    print("场景数 S 的敏感性（对场景集覆盖能力的影响，取全年平均）")
    print("=" * 80)
    print(f"  {'S':>5}{'场景均值偏离(kWh)':>20}{'80%分位高于点预测(kWh)':>26}")
    for S in [5, 10, 20, 30, 40, 56]:
        dev, cov = [], []
        for dd in range(TRAIN_FROM, 365, 7):
            fc = best.predict(L, V, dd)
            scen, w = build_scenarios(R, dd, fc, S=S)
            st = scenario_stats(scen, w, fc)
            dev.append(st["mean_deviation_kWh"])
            cov.append(st["p80_above_fc_kWh"])
        print(f"  {S:>5}{np.mean(dev):>20.1f}{np.mean(cov):>26.1f}")

    print("\n  注：S=56 即不做削减的原始窗口")
