"""校验：当前工作区 question1/results（定义一，往返 0.81）是否仍与 git 已提交结果一致。

目录重构后 def1 直接写回 question1/results（不另存副本），故本脚本改为
「工作区现值 vs git HEAD 版本」的比对，用于确认重跑或代码修改后结果未变。

用法（在 question1/efficiency/code 下）：
    python -X utf8 verify_def1.py
输出同时写入 question1/efficiency/verification_def1.txt（UTF-8 直写，
避免 PowerShell 管道导致的不可逆双重编码损坏）。
"""
import io
import pathlib
import subprocess

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[3]
RES = REPO / "question1" / "results"

_lines = []


def out(s=""):
    print(s)
    _lines.append(s)


out("=" * 78)
out("定义一（往返 0.81）与 git 已提交结果的一致性校验")
out("=" * 78)
out(f"仓库：{REPO}")
out(f"结果：{RES}")


def _git_show(relpath):
    r = subprocess.run(["git", "show", f"HEAD:{relpath}"],
                       cwd=REPO, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(
            f"无法读取 HEAD:{relpath}\n{r.stderr.decode('utf-8', 'replace')}")
    return r.stdout


# ---- solution.npz：git HEAD vs 工作区 ----
a = np.load(io.BytesIO(_git_show("question1/results/solution.npz")),
            allow_pickle=True)
b = np.load(RES / "solution.npz", allow_pickle=True)
out(f"\n{'键':<12}{'最大绝对差':>18}")
ok_all = True
for k in ["price", "load", "pv", "g", "c", "d", "w", "E"]:
    if k not in a.files or k not in b.files:
        continue
    dmax = float(np.max(np.abs(a[k].astype(float) - b[k].astype(float))))
    ok = dmax < 1e-9
    ok_all &= ok
    out(f"  {k:<10}{dmax:>18.3e}  {'✓' if ok else '✗'}")
for k in ["obj_lp", "obj_milp", "base_cost"]:
    va, vb = float(a[k]), float(b[k])
    ok = abs(va - vb) < 1e-6
    ok_all &= ok
    out(f"  {k:<10}{abs(va-vb):>18.3e}  {'✓' if ok else '✗'}   ({va:,.2f} vs {vb:,.2f})")

# ---- 明细 CSV 比对（git HEAD vs 工作区）----
da = pd.read_csv(io.BytesIO(_git_show("question1/results/schedule_detail.csv")))
db = pd.read_csv(RES / "schedule_detail.csv")
out(f"\n  schedule_detail.csv  形状 {da.shape} vs {db.shape}")
num_cols = [c for c in da.columns if da[c].dtype.kind in "fi"]
worst = 0.0
for c in num_cols:
    dm = float(np.max(np.abs(da[c] - db[c])))
    worst = max(worst, dm)
out(f"  全部数值列最大差 = {worst:.3e}  "
    f"{'✓ 完全一致' if worst < 1e-6 else '✗'}")

out("\n" + "=" * 78)
out(f"结论：{'✓ 工作区结果与 git HEAD 逐值一致' if ok_all and worst < 1e-6 else '✗ 存在差异'}")
out("=" * 78)

# ---- 落盘（直写 UTF-8，避免 PowerShell 管道双重编码损坏）----
dst = REPO / "question1" / "efficiency" / "verification_def1.txt"
dst.write_text("\n".join(_lines) + "\n", encoding="utf-8")
print(f"\n已写入 {dst}")
