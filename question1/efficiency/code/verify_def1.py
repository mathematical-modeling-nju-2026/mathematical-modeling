"""校验：efficiency/def1_side90 的结果与仓库原有 question1/results 是否逐时段一致。"""
import pathlib

import numpy as np
import pandas as pd

REPO = pathlib.Path(r"d:\数学建模大赛\mathematical-modeling")
OLD = REPO / "question1" / "results"
NEW = REPO / "question1" / "efficiency" / "def1_side90" / "results"

print("=" * 78)
print("定义一（往返 0.81）与仓库原有结果的一致性校验")
print("=" * 78)

# ---- solution.npz 逐时段比对 ----
a = np.load(OLD / "solution.npz", allow_pickle=True)
b = np.load(NEW / "solution.npz", allow_pickle=True)
print(f"\n{'键':<12}{'最大绝对差':>18}")
ok_all = True
for k in ["price", "load", "pv", "g", "c", "d", "w", "E"]:
    if k not in a.files or k not in b.files:
        continue
    dmax = float(np.max(np.abs(a[k].astype(float) - b[k].astype(float))))
    ok = dmax < 1e-9
    ok_all &= ok
    print(f"  {k:<10}{dmax:>18.3e}  {'✓' if ok else '✗'}")
for k in ["obj_lp", "obj_milp", "base_cost"]:
    va, vb = float(a[k]), float(b[k])
    ok = abs(va - vb) < 1e-6
    ok_all &= ok
    print(f"  {k:<10}{abs(va-vb):>18.3e}  {'✓' if ok else '✗'}   ({va:,.2f} vs {vb:,.2f})")

# ---- 明细 CSV 比对 ----
da = pd.read_csv(OLD / "schedule_detail.csv")
db = pd.read_csv(NEW / "schedule_detail.csv")
print(f"\n  schedule_detail.csv  形状 {da.shape} vs {db.shape}")
num_cols = [c for c in da.columns if da[c].dtype.kind in "fi"]
worst = 0.0
for c in num_cols:
    dm = float(np.max(np.abs(da[c] - db[c])))
    worst = max(worst, dm)
print(f"  全部数值列最大差 = {worst:.3e}  {'✓ 完全一致' if worst < 1e-6 else '✗'}")

# ---- 与 git 中原提交版本比对 ----
import subprocess
raw = subprocess.run(["git", "show", "HEAD:question1/results/solution.npz"],
                     cwd=REPO, capture_output=True)
if raw.returncode == 0:
    import io
    g = np.load(io.BytesIO(raw.stdout), allow_pickle=True)
    gm = max(float(np.max(np.abs(g[k].astype(float) - b[k].astype(float))))
             for k in ["g", "c", "d", "w", "E"])
    print(f"\n  与 git HEAD 版本比对：最大差 = {gm:.3e}  "
          f"{'✓ 与已提交结果一致' if gm < 1e-9 else '✗'}")

print("\n" + "=" * 78)
print(f"结论：{'✓ 定义一精确复现仓库原有结果' if ok_all and worst < 1e-6 else '✗ 存在差异'}")
print("=" * 78)
