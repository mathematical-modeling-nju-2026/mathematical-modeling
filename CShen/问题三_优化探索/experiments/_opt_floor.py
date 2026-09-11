"""实验：放松/移除"计划净供给 ≥ 点预测"下界，看是否减少 dump 与总费用。"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE / "_peer_lab"
sys.path.insert(0, str(LAB))

import q3_data, q3_forecast, q3_model          # noqa: E402
import run_q3 as RUN                            # noqa: E402


def run(label, **flags):
    for k, v in flags.items():
        q3_model.FLAGS[k] = v
    f = q3_forecast.Forecaster(q3_data.load_data())
    detail, days, summary, trees = RUN.simulate(f, 'all', end=365)
    print(f"[{label}] 总={summary['total_cost_yuan']/1e4:9.2f}万 "
          f"计划={summary['planned_cost_yuan']/1e4:8.2f} "
          f"调整={summary['adjustment_net_yuan']/1e4:7.2f} "
          f"紧急={summary['emergency_cost_yuan']/1e4:7.2f} "
          f"dump={summary['dump_kwh']/1e4:7.2f} "
          f"orig={summary['original_kwh']/1e4:7.2f}", flush=True)
    return summary


if __name__ == "__main__":
    res = {}
    res["基线"] = run("基线(下界=点预测)", no_floor=False, floor_ratio=1.0)
    res["下界=0.8×点预测"] = run("下界=0.8×点预测", no_floor=False, floor_ratio=0.8)
    res["下界=0.5×点预测"] = run("下界=0.5×点预测", no_floor=False, floor_ratio=0.5)
    res["无下界"] = run("无下界", no_floor=True, floor_ratio=1.0)
    (HERE / "_opt_floor.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    base = res["基线"]["total_cost_yuan"]
    print()
    for k, v in res.items():
        print(f"  {k:<16}{v['total_cost_yuan']/1e4:9.2f} 万  "
              f"Δ={(v['total_cost_yuan']-base)/1e4:+7.2f} 万  "
              f"dump={v['dump_kwh']/1e4:7.2f}")
