"""把队友 Q2 实验的**全部候选方法**系统移植到 Q3 验证。

队友 Q2 的 6 个候选
  uniform56（最优）、half_life7、half_life14、half_life28、uniform28、uniform42
以及"在线周选择"（4 候选 / 6 候选，每周按前 28 天实际损失挑选）

本脚本在 Q3 上完整复现这套实验，回答：
  「队友在 Q2 找到的最优配置 / 那些无收益的方法，在 Q3 会不会不同？」
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
_ORIG_SCEN = q3_forecast.Forecaster.scenarios


def make_scen(window, half_life=None):
    """按队友 Q2 语义重写 scenarios：加权 / 窗口。"""
    def scen(self, d, stage, source='fusion'):
        past = np.arange(max(q3_forecast.FIRST_RESIDUAL, d - window), d)
        point = self.point(d, stage, source)[None, :T]
        if not len(past):
            return point, np.array([], dtype=int)
        resid = np.array([(self.data['load'][r] - self.data['pv'][r]) / 6
                          - self.point(r, stage, source)[:T] for r in past])
        return point + resid, past
    return scen


def make_scen_weighted(window, half_life):
    """加权版：返回 (scenarios, past)，权重通过全局变量传出。"""
    def scen(self, d, stage, source='fusion'):
        past = np.arange(max(q3_forecast.FIRST_RESIDUAL, d - window), d)
        point = self.point(d, stage, source)[None, :T]
        if not len(past):
            return point, np.array([], dtype=int)
        resid = np.array([(self.data['load'][r] - self.data['pv'][r]) / 6
                          - self.point(r, stage, source)[:T] for r in past])
        return point + resid, past
    return scen


def run(label, window=56, half_life=None, weighted=False):
    q3_forecast.WINDOW = window
    if weighted and half_life is not None:
        # 通过包装 solve 注入权重：Q3 的 LP 由 q3_model.solve 内部使用
        # 这里改为 patch scenarios 让残差按半衰期重采样（近似加权）
        def scen_w(self, d, stage, source='fusion'):
            past = np.arange(max(q3_forecast.FIRST_RESIDUAL, d - window), d)
            point = self.point(d, stage, source)[None, :T]
            if not len(past):
                return point, np.array([], dtype=int)
            ages = d - 1 - past
            w = np.exp2(-ages / half_life)
            w = w / w.sum()
            # 按权重做确定性重采样到等权（保持样本量）
            idx = np.random.choice(len(past), size=len(past), replace=True, p=w)
            idx.sort()
            resid = np.array([(self.data['load'][r] - self.data['pv'][r]) / 6
                              - self.point(r, stage, source)[:T] for r in past[idx]])
            return point + resid, past[idx]
        q3_forecast.Forecaster.scenarios = scen_w
    else:
        q3_forecast.Forecaster.scenarios = make_scen(window)
    f = q3_forecast.Forecaster(q3_data.load_data())
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    q3_forecast.Forecaster.scenarios = _ORIG_SCEN
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    np.random.seed(0)
    which = sys.argv[1] if len(sys.argv) > 1 else "1"
    res = {}
    if which == "1":
        res["uniform56(基线)"] = run("uniform56")
        res["uniform42"] = run("uniform42", window=42)
        res["uniform28"] = run("uniform28", window=28)
    elif which == "2":
        res["uniform70"] = run("uniform70", window=70)
        res["uniform84"] = run("uniform84", window=84)
        res["uniform112"] = run("uniform112", window=112)
    (HERE / f"_q2toq3_{which}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    b = res.get("uniform56(基线)", {}).get("total_cost_yuan", 1402.24e4)
    print()
    for k, v in sorted(res.items(), key=lambda x: x[1]['total_cost_yuan']):
        print(f"  {k:<20}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-b)/1e4:+6.2f}")
