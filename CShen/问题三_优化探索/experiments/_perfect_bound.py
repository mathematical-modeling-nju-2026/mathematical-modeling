"""计算问题三的**完美预见下界**：若每天完全知道实际净负载，最优费用是多少。

用途
  · 量化"预报误差"造成的成本（= 完美预见费用 与 实际费用之差）
  · 判断同伴方案 1402.24 万离理论下界还有多远
框架：与 Q2/Q3 相同的物理约束（储能、电价、紧急购电 5p、计划/调整计费），
      唯一区别是**每天的净负载点预测 = 当日实际净负载**（其余不变）。
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from q3_data import load_price, load_actual, T, DT
from q3_model import solve_plan_24h, ETA, EMG

price = load_price()
L, PV = load_actual()
N = L - PV
ND = L.shape[0]
START = 31
E_INIT = 6000.0


def perfect_foresight(adjust_stages=(1, 2, 3)):
    """完美预见：0:00 计划即用当日实际净负载；调整阶段也用实际。"""
    E_now = E_INIT
    tot = np.zeros(3)
    for d in range(START, ND):
        E0 = E_now
        Nk = N[d] * DT                          # 实际净负载（kWh/时段）
        # 完美预见的"计划"：直接按实际求解（单场景、等式）
        segs = [Nk]
        for j in range(d + 1, min(d + 2, ND)):
            segs.append(N[j] * DT)
        N_plan = np.concatenate(segs)
        plan = solve_plan_24h(N_plan, Nk.reshape(1, -1), np.array([1.0]),
                              price, E0, E0)
        gp, cp, dp = plan["g"][:T], plan["c"][:T], plan["d"][:T]
        z = gp + dp - cp
        e = np.maximum(Nk - z, 0.0)
        tot[0] += float(price @ gp)
        tot[2] += float(EMG * (price @ e))
        E_now = E0 + np.sum(ETA * cp - dp / ETA)
    return tot


print("计算完美预见下界（每天知道实际净负载）...")
t = perfect_foresight()
print(f"  计划费 {t[0]/1e4:9.2f} 万")
print(f"  紧急费 {t[2]/1e4:9.2f} 万")
print(f"  合计   {t.sum()/1e4:9.2f} 万")
print()
print("对比：")
print(f"  同伴方案（0/6/12/18）   1402.24 万")
print(f"  完美预见下界            {t.sum()/1e4:9.2f} 万")
print(f"  ⇒ 预报误差成本（可提升空间） {(1402.24 - t.sum()/1e4):8.2f} 万")
(HERE / "_q3_perfect_bound.json").write_text(json.dumps(
    dict(plan=t[0], emg=t[2], total=float(t.sum()),
         total_wan=float(t.sum() / 1e4),
         peer=1402.24, gap_wan=float(1402.24 - t.sum() / 1e4)),
    ensure_ascii=False, indent=2), encoding="utf-8")
