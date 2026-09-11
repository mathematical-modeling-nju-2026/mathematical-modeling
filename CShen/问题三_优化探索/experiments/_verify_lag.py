"""验证 lag 源映射正确性（在 _peer_lab 目录下运行，避免模块冲突）。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE / "_peer_lab"
sys.path.insert(0, str(LAB))

import q3_data, q3_forecast            # noqa: E402
import importlib.util                   # noqa: E402

spec = importlib.util.spec_from_file_location("m2", HERE / "_opt_multi2.py")
m2 = importlib.util.module_from_spec(spec)
sys.modules["m2"] = m2
spec.loader.exec_module(m2)

f = q3_forecast.Forecaster(q3_data.load_data())
srcs = m2.build_lag_sources(f, max_lag=2)

d = 100
ok0 = np.allclose(np.nan_to_num(srcs[1][d, 0, 0:108]),
                  np.nan_to_num(f.raw[d - 1, 3, 144:252]), atol=1e-6)
ok1 = np.allclose(np.nan_to_num(srcs[1][d, 2, 72:180]),
                  np.nan_to_num(f.raw[d, 1, 72:180]), atol=1e-6)
print("lag1 stage0 与前一日18:00一致:", ok0)
print("lag1 stage2 与当期前一期一致:", ok1)
print("lag1 可用帧数(日100,stage0):", int(np.isfinite(srcs[1][100, 0]).sum()), "/288")
print("lag2 可用帧数(日100,stage0):", int(np.isfinite(srcs[2][100, 0]).sum()), "/288")
print("lag1 可用帧数(日100,stage3):", int(np.isfinite(srcs[1][100, 3]).sum()), "/288")
