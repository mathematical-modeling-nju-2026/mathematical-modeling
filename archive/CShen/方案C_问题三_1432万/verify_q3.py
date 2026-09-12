"""问题3 结果可行性校验。"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from q3_data import load_actual, T, DT

ATT = Path(r"d:\数学建模大赛\CUMCM2026Problems\C题\附件")
ETA = 0.90
E_MIN, E_MAX = 1200.0, 10800.0
P_MAX = 5000.0
FLOW_CAP = P_MAX * DT
EMG = 5.0

d = np.load(HERE / "_q3_result.npz", allow_pickle=True)
g_plan = d["g_plan"]; g_final = d["g_final"]
c = d["c"]; dd = d["d"]; e = d["e"]
E_start = d["E_start"]; E_end = d["E_end"]; N = d["N"]; price = d["price"]

L, PV = load_actual()
na = N  # (334,144) kW
checks = {}

z = g_final + dd - c                         # 最终净供给
checks["power_flow_cap_charge"] = float(c.max())
checks["power_flow_cap_discharge"] = float(dd.max())
checks["simultaneous_cd_periods"] = int(((c > 1e-6) & (dd > 1e-6)).sum())
checks["grid_nonneg"] = bool((g_final >= -1e-7).all() and (g_plan >= -1e-7).all())

# SOC 轨迹重建
E = np.zeros((c.shape[0], T + 1))
for i in range(c.shape[0]):
    E[i, 0] = E_start[i]
    E[i, 1:] = E_start[i] + np.cumsum(ETA * c[i] - dd[i] / ETA)
checks["E_min"] = float(E.min()); checks["E_max"] = float(E.max())
checks["cross_day_max_dev"] = float(np.abs(E[:-1, -1] - E[1:, 0]).max())

# 紧急购电 = 实际缺口
deficit = np.maximum(na * DT - z, 0.0)
checks["emergency_equals_deficit_max_dev"] = float(np.abs(e - deficit).max())

# 非负
checks["u_nonneg"] = bool((np.maximum(g_final - g_plan, 0) >= -1e-9).all())

checks["pass"] = bool(
    checks["power_flow_cap_charge"] <= FLOW_CAP + 1e-6
    and checks["power_flow_cap_discharge"] <= FLOW_CAP + 1e-6
    and checks["simultaneous_cd_periods"] == 0
    and checks["grid_nonneg"]
    and checks["E_min"] >= E_MIN - 1e-6
    and checks["E_max"] <= E_MAX + 1e-6
    and checks["cross_day_max_dev"] <= 1e-6
    and checks["emergency_equals_deficit_max_dev"] <= 1e-6
)

print(json.dumps(checks, ensure_ascii=False, indent=2))
(HERE / "_q3_verification.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
