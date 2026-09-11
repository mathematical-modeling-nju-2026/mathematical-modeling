"""实验：18:00（最后一次发布）的预报覆盖次日 0:00-18:00，目前完全未被利用。

同伴 solve 在 stop==T 时加入"次日确定性模型"，但次日 node_point 用的是
**历史预测**（f.point 的次日部分来自 hist/fused 的 d 行 288 长拼接，
fused[d,stage] 只覆盖当天 [stage*36, stage*36+144)，跨午夜后自动回落到 hist）。

改进：在 18:00 节点，次日 0:00-18:00 段改用**当日 18:00 发布的预报**
（external[d,3,:18]），使 18:00 的信息真正影响次日储能安排。
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
ORIG_SOLVE = q3_model.solve


def nextday_point_from_issue(f, day, stage, idx_lo, idx_hi):
    """次日 [idx_lo, idx_hi) 段的点预测，用 day 日 stage 发布预报（若有覆盖）。"""
    # external[day, stage] 覆盖 [stage*36, stage*36+144) 的整点；跨午夜部分即次日
    start = stage * 36
    out = f.point(day, stage)[T:T + idx_hi]      # 历史基预测（次日部分）
    # 用发布预报覆盖次日 0:00 起的可见部分
    ext = f.data['external'][day, stage]          # 24 个整点值
    anchor = np.array([f.hist[day, start - 1] if start else 0.0])
    for k in range(1, 25):
        pos = start + k * 6
        if pos < T:
            continue
        j = pos - T                              # 次日 10min 索引
        if j >= idx_hi:
            break
        # 线性插值到 10min
        prev_pos = pos - 6
        prev_val = (ext[k - 2] if k >= 2 else anchor[0]) if prev_pos >= T else None
        out[j] = ext[k - 1] if j % 6 == 0 else out[j]
    # 简化为：逐 10min 用相邻整点线性插值
    marks, vals = [], []
    for k in range(1, 25):
        pos = start + k * 6
        if pos >= T and (pos - T) <= idx_hi:
            marks.append(pos - T); vals.append(ext[k - 1])
    if marks:
        marks = np.array(marks); vals = np.array(vals)
        t = np.arange(len(out))
        m = (t >= marks[0]) & (t <= marks[-1])
        out[m] = np.interp(t[m], marks, vals)
    return out


def run(label, use_issue_nextday=False):
    q3_model.solve = ORIG_SOLVE
    if not use_issue_nextday:
        f = q3_forecast.Forecaster(q3_data.load_data())
        detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    else:
        # monkeypatch: 仅当 stage==3 时，把次日前瞻的 node_point 换成发布预报
        def patched(forecaster, day, stage, stages, energy, day_start_energy,
                    original=None, source='fusion', deterministic=False,
                    branch=True):
            if stage == 3 and day < len(forecaster.data['load']) - 1:
                # 临时替换 point 的次日部分
                orig_point = forecaster.point

                def point_with_issue(d, s, src='fusion'):
                    v = orig_point(d, s, src)
                    if d == day and s == stage:
                        nxt = nextday_point_from_issue(forecaster, day, 3, 0, T)
                        v = v.copy(); v[T:] = nxt
                    return v
                forecaster.point = point_with_issue
                try:
                    return ORIG_SOLVE(forecaster, day, stage, stages, energy,
                                      day_start_energy, original, source,
                                      deterministic, branch)
                finally:
                    forecaster.point = orig_point
            return ORIG_SOLVE(forecaster, day, stage, stages, energy,
                              day_start_energy, original, source,
                              deterministic, branch)
        q3_model.solve = patched
        RUN.solve = patched
        f = q3_forecast.Forecaster(q3_data.load_data())
        detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    res = {}
    res["基线"] = run("基线")
    res["18:00预报用于次日"] = run("18:00预报用于次日", True)
    (HERE / "_opt_nextday.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
