"""单调整时点贡献分析。"""
from __future__ import annotations
import sys, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_q3 as R

out = {}
print("不调整 ..."); out["A"] = R.summarize(R.simulate(use_adjust=False, verbose=False))
for nm, st in [("仅6:00", (1,)), ("仅12:00", (2,)), ("仅18:00", (3,)),
               ("6+12", (1, 2)), ("12+18", (2, 3)), ("6+18", (1, 3)),
               ("6+12+18", (1, 2, 3))]:
    print(f"{nm} ...")
    out[nm] = R.summarize(R.simulate(use_adjust=True, verbose=False, adjust_stages=st))

a = out["A"]["total"]
print()
print(f"{'方案':<12}{'合计(万)':>10}{'节省(万)':>10}")
for k, s in out.items():
    print(f"{k:<12}{s['total_wan']:>10.2f}{(a-s['total'])/1e4:>10.2f}")
(HERE / "_q3_single_stage.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
