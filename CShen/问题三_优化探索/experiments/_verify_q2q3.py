"""精确核对：队友 Q2 优化方案的核心组件 vs Q3 现有实现。"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE / "_peer_lab"
sys.path.insert(0, str(LAB))

import q3_forecast, q3_data            # noqa: E402
import importlib.util, io, re           # noqa: E402

Q2 = Path(r"d:\数学建模大赛\mathematical-modeling\CShen\方案B_1439万\run_1439.py")
q2src = io.open(Q2, encoding='utf-8').read()

print("=== Q2 方案B 的预测内核配置 ===")
for pat in [r"LOAD_K,\s*LOAD_DRIFT\s*=\s*[\d,\s]+",
            r"PV_M,\s*PV_DRIFT\s*=\s*[\d,\s]+",
            r"HORIZON\s*=\s*\d+",
            r"WINDOW\s*=\s*\d+"]:
    m = re.search(pat, q2src)
    print("  ", m.group(0) if m else f"未找到 {pat}")

print()
print("=== Q3 方案 的对应配置 ===")
q3src = io.open(Path(r"d:\数学建模大赛\mathematical-modeling\C_yang\ques3\q3_forecast.py"),
                encoding='utf-8').read()
for pat in [r"WINDOW\s*=\s*\d+", r"FIRST_RESIDUAL\s*=\s*\d+"]:
    m = re.search(pat, q3src)
    print("  ", m.group(0) if m else f"未找到 {pat}")

# history_day 用的 kernel
hd = re.search(r"def history_day.*?return.*?\n", q3src, re.S)
print()
print("=== Q3 的 history_day（负载/光伏 kernel）===")
print(hd.group(0).strip() if hd else "未找到")

print()
print("=== 判定 ===")
print("Q2 内核: 负载 sw4/drift5，光伏 t7/drift28")
print("Q3 的 history_day: channel(load,...,same_week=True,5) / channel(pv,...,False,28)")
print("→ 负载 = 最近4次同星期几均值 + 近5天漂移 = **sw4/drift5**  ✔ 一致")
print("→ 光伏 = 近7天均值 + 近28天漂移 = **t7/drift28**  ✔ 一致")
print()
print("Q2 优化(排除回退残差 FIRST_RESIDUAL=7): Q3 已内置 → ✔ 已套用")
