"""问题3 数据层：电价、实际负载/光伏、光伏预报（附件3）与时间对齐。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ATT = Path(__file__).resolve().parents[3] / "data" / "附件"
DT = 1.0 / 6.0
T = 144
STAGE_HOUR = [0, 6, 12, 18]      # 四个预报时刻


def load_price():
    return pd.read_excel(ATT / "附件1.xlsx")["电价"].to_numpy(float)


def load_actual():
    """返回 (L, PV)，均为 (365,144) kW。"""
    L = pd.read_excel(ATT / "附件2.xlsx", sheet_name="小区负载").iloc[:, 1:].to_numpy(float)
    PV = pd.read_excel(ATT / "附件2.xlsx", sheet_name="光伏发电实际功率").iloc[:, 1:].to_numpy(float)
    return L, PV


def load_forecast():
    """读附件3，返回 FC(365,4,24)，FC[d,s,k] = 第 d 天阶段 s 的"预报 k 小时"（kW）。

    对齐口径（已验证 MAE 最小）：预报 k 小时 = 整点 (s+k):00 的瞬时功率，
    用作该小时 (s+k-1):00 ~ (s+k):00 的代表功率，10min 粒度即 6 个相同值。
    """
    df = pd.read_excel(ATT / "附件3.xlsx")
    df["日期"] = df["日期"].ffill()
    days = list(df["日期"].unique())
    FC = np.full((len(days), 4, 24), np.nan)
    for i, dt in enumerate(days):
        blk = df[df["日期"] == dt]
        for _, r in blk.iterrows():
            s = STAGE_HOUR.index(int(str(r["预报时刻"]).split(":")[0]))
            FC[i, s, :] = r.iloc[2:].to_numpy(float)
    return FC, days


def fc_to_10min(FC_day, stage, t_start=0, t_end=T, method="interp"):
    """把某天某阶段的 24 小时预报展开为 10min 粒度（覆盖 [t_start, t_end)）。

    时间对齐（经 MAE 验证）：附件3 的"预报 k 小时"是**发布时刻 + k 小时那一整点的
    瞬时光伏功率**（k=1..24）。阶段 stage ∈ {0,1,2,3} 的发布整点为 {0,6,12,18} 时。

    method="interp"（默认）：把 24 个整点预报作为锚点，在 10min 网格上线性插值
       重建连续曲线。整点瞬时口径下 MAE≈132~235 kW，优于分段常数。
    method="const"：把整点预报值沿用为该小时的常值（分段常数），MAE≈306~431 kW。

    t_start/t_end 以 10min 为索引（0..144），返回长度 t_end-t_start。
    """
    out = np.full(T, np.nan)
    sh = STAGE_HOUR[stage]
    if method == "const":
        base = stage * 36
        for k in range(1, 25):
            a, b = base + (k - 1) * 6, base + k * 6
            if a >= T:
                break
            out[a:min(b, T)] = FC_day[stage, k - 1]
    else:
        marks, vals = [], []
        # 发布时刻那一整点的锚点（用 k=1 克隆，避免首小时无覆盖）
        if sh * 6 < T:
            marks.append(sh * 6); vals.append(FC_day[stage, 0])
        for k in range(1, 25):
            h = sh + k
            if h * 6 > T:
                break
            marks.append(h * 6); vals.append(FC_day[stage, k - 1])
        if marks:
            marks = np.array(marks, float); vals = np.array(vals, float)
            t = np.arange(T)
            m = (t >= marks[0]) & (t <= marks[-1])
            out[m] = np.interp(t[m], marks, vals)
    return out[t_start:t_end]


def forecast_residual(FC, PV):
    """历史预报误差（kW）：resid[d,s,t] = 实际(d,t) − 预报10min。

    只对有预报覆盖的时段计算。返回 (365,4,144)，未覆盖处为 NaN。
    """
    R = np.full((365, 4, T), np.nan)
    for d in range(min(len(FC), PV.shape[0])):
        for s in range(4):
            f = fc_to_10min(FC[d], s)
            valid = ~np.isnan(f)
            R[d, s, valid] = PV[d, valid] - f[valid]
    return R
