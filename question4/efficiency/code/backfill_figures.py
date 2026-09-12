"""为各效率口径补齐图表（复用各问原始绘图逻辑，仅重定向输出根）。

  Q1     question1/code/plot_q1.py      → figs/fig1_dispatch.*、fig2_comparison.*
  Q3     question3/code/plot_q3.py      → figures/cost_comparison.*、
                                          forecast_fusion.*、target_dispatch.*
  Q4-3   question4/part3/code/plot_q3.py → 同上

Q2 的窗宽对照图 window_comparison.* 由 report_experiment.py 内联绘制，
其 def1 专用断言（原基线必须精确等于 common/q2_base）在 def2 不成立，
故由 backfill_q2_eff.py 另做处理，此处不涉及。

不修改任何原始文件；只做运行期模块属性覆盖。

用法
    python backfill_figures.py --q q1  --eff def1_side90
    python backfill_figures.py --q q3  --eff def2_roundtrip90
    python backfill_figures.py --q q43 --eff def1_side90
    python backfill_figures.py --all
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "common" / "plotting"
ETA_DIR = REPO / "common" / "efficiency"
for p in (COMMON, ETA_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("CUMCM_C_ATTACHMENT_DIR", str(REPO / "data" / "附件"))

from eta_common import results_dir  # noqa: E402

EFFS = ("def1_side90", "def2_roundtrip90")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def do_q1(eff: str) -> None:
    """问题1 图：plot_q1.py 无入参、在 `__main__` 分支里创建 FIGS 并绘图。

    因此要把 HERE 与 FIGS 两个模块常量都重定向到口径目录，再手动执行
    其 `__main__` 分支的两步（建目录 + 绘图），避免 `runpy` 带来的副作用。
    """
    code = REPO / "question1" / "code"
    out = results_dir("question1", eff, REPO)
    if eff == "def1_side90":
        raise RuntimeError("def1 即基线，其图已在 question1/results/figs；"
                           "重新生成会覆盖基线文件，已阻止")
    if str(code) not in sys.path:
        sys.path.insert(0, str(code))
    mod = load_module(code / "plot_q1.py", f"plot_q1_{eff}")
    mod.HERE = out
    mod.FIGS = out / "figs"
    mod.FIGS.mkdir(parents=True, exist_ok=True)
    d = mod.load_data()
    for p in mod.fig1_dispatch(d) + mod.fig2_comparison(d):
        print(f"    已导出: {p}")
    print(f"  [Q1 {eff}] figs -> {mod.FIGS}")


def do_q3(eff: str, which: str) -> None:
    """问题3 / 4-3 图。

    注意：`plot_q3.py` 的输出根 `HERE` 在两次远端提交间改过写法：
      · 旧版：`from q3_data import HERE`（需先污染 q3_data.HERE）
      · 新版：`HERE = Path(__file__).resolve().parents[1] / 'results'`（模块级常量）
    新版下污染 q3_data 无效，会导致图**误写入基线 results/**。
    因此这里统一采用「载入后覆盖模块属性」——两种写法都成立，
    并在绘图后断言输出确实落在目标目录，防止再次静默写错位置。
    """
    if which == "q3":
        code = REPO / "question3" / "code"
        out = results_dir("question3", eff, REPO)
    else:
        code = REPO / "question4" / "part3" / "code"
        out = results_dir("question4/part3", eff, REPO)

    if eff == "def1_side90":
        raise RuntimeError("def1 即基线，其图已在基线 results/figures；"
                           "重新生成会覆盖基线文件，已阻止")
    if str(code) not in sys.path:
        sys.path.insert(0, str(code))
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    plot = load_module(code / "plot_q3.py", f"plot_q3_fig_{which}_{eff}")
    # 覆盖模块级常量（main() 在函数体内读取 HERE，故此处覆盖生效）
    plot.HERE = out
    if hasattr(plot, "FIG"):
        plot.FIG = figs

    before = {p.name: p.stat().st_mtime for p in figs.glob("*")}
    plot.main()
    after = {p.name: p.stat().st_mtime for p in figs.glob("*")}

    if not after:
        raise RuntimeError(f"{which} 绘图后目标目录仍为空: {figs}——输出可能写到了别处")
    if after == before:
        raise RuntimeError(f"{which} 绘图未更新任何文件: {figs}")

    print(f"  [{which.upper()} {eff}] figures -> {figs}"
          f"（{len(after)} 个文件，已确认写入目标目录）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", choices=["q1", "q3", "q43"])
    ap.add_argument("--eff", default="def2_roundtrip90", choices=list(EFFS))
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    jobs = []
    if args.all:
        for e in EFFS:
            jobs += [("q1", e), ("q3", e), ("q43", e)]
    else:
        if not args.q:
            raise SystemExit("请给出 --q，或使用 --all")
        jobs = [(args.q, args.eff)]

    for which, eff in jobs:
        # def1 的结果目录就是基线 results/ 本身，其图已存在且逐字节相同。
        # 重新生成只会覆盖基线文件（曾因此污染仓库），故直接跳过。
        if eff == "def1_side90":
            print(f"== {which} / {eff}  —— 跳过：def1 即基线，其图已在 results/ 中")
            continue
        print(f"== {which} / {eff}")
        if which == "q1":
            do_q1(eff)
        elif which == "q3":
            do_q3(eff, "q3")
        else:
            do_q3(eff, "q43")


if __name__ == "__main__":
    main()
