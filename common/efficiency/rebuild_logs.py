"""只读重放：从已有结果重建干净的 run_log，不做任何重新求解。

安全性
    本脚本只读取既有结果文件并打印摘要，再用 subprocess 抓原始字节写日志，
    **绝不调用求解器，绝不修改任何结果文件**（结果文件 mtime 不变可验证）。

用法
    python rebuild_logs.py            # 重建全部 5 个日志
    python rebuild_logs.py --check    # 只核对编码，不写文件
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eta_common import EFF_DEFS, results_dir  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

JOBS = [
    ("question1", "question1/efficiency/results/run_log.txt", "一"),
    ("question2", "question2/efficiency/run_log.txt", "二"),
    ("question3", "question3/efficiency/run_log.txt", "三"),
    ("question4/part2", "question4/efficiency/part2_run_log.txt", "四-2"),
    ("question4/part3", "question4/efficiency/part3_run_log.txt", "四-3"),
]

HEADER = """\
============================================================================
{title}
============================================================================
效率口径   : {key}
定义       : {label}
递推式     : {note}
η_c = {eta_c:.6f}   η_d = {eta_d:.6f}   往返 = {rt:.6f}
结果目录   : {out}
生成方式   : 本日志由 rebuild_logs.py 从既有结果文件只读重建
             （原始日志因 PowerShell 管道编码问题损坏，未能保留；
               数值结果与校验文件不受影响）
============================================================================
"""


def summaries(q: str, key: str) -> list[tuple[str, str]]:
    """从既有结果文件读出关键数值，作为日志正文。"""
    d = results_dir(q, key, REPO)
    rows: list[tuple[str, str]] = []

    if q == "question1":
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        rows += [("全天购电费（元）", f"{s['obj_milp_yuan']:,.2f}"),
                 ("全天购电量（kWh）", f"{s['g_kwh']:,.2f}"),
                 ("充电量（kWh）", f"{s['c_kwh']:,.2f}"),
                 ("放电量（kWh）", f"{s['d_kwh']:,.2f}"),
                 ("往返损失（kWh）", f"{s['roundtrip_loss_kwh']:,.2f}"),
                 ("较无储能基线节省（元）", f"{s['saving_yuan']:,.2f}"),
                 ("节省比例", f"{s['saving_percent']:.2f}%"),
                 ("自检通过", str(s.get("checks_pass")))]
    elif q == "question2":
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        rows += [("天数", str(s.get("days"))),
                 ("最初/末日", f"{s.get('report_start','?')} ~ {s.get('report_end','?')}"),
                 ("计划购电量（kWh）", f"{s.get('g_kwh', float('nan')):,.2f}"),
                 ("紧急购电量（kWh）", f"{s.get('emergency_kwh', float('nan')):,.2f}"),
                 ("总费用（元）", f"{s['total_cost_yuan']:,.2f}")]
    elif q in ("question3", "question4/part3"):
        import pandas as pd
        c = pd.read_csv(d / "comparison.csv")
        for _, r in c.iterrows():
            rows.append((f"  {r.get('mode','?')}", f"{r['total_cost_yuan']:,.2f} 元"))
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        rows.append(("主方案总费用（元）", f"{s.get('total_cost_yuan', float('nan')):,.2f}"))
    else:  # question4/part2
        for name in ("q2_repriced", "mean_price", "joint_price", "known_today_price"):
            p = d / "variants" / name / "summary.json"
            if p.exists():
                s = json.loads(p.read_text(encoding="utf-8"))
                rows.append((f"  {name}", f"{s['total_cost_yuan']:,.2f} 元"))

    for name in ("efficiency_verification.json", "verification.json",
                 "verification_all.json", "information_verification.json",
                 "publication_verification.json"):
        p = d / name
        if p.exists():
            j = json.loads(p.read_text(encoding="utf-8"))
            rows.append((f"[校验] {name}", str(j.get("pass", j.get("pass_check")))))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    for q, logrel, disp in JOBS:
        key = "def2_roundtrip90"
        log = REPO / logrel
        eta_c, eta_d, rt, label, note = (
            EFF_DEFS[key]["eta_c"], EFF_DEFS[key]["eta_d"],
            EFF_DEFS[key]["roundtrip"], EFF_DEFS[key]["label"],
            EFF_DEFS[key]["note"])
        body = HEADER.format(title=f"问题{disp}  效率口径 = {key}", key=key,
                             label=label, note=note, eta_c=eta_c,
                             eta_d=eta_d, rt=rt,
                             out=results_dir(q, key, REPO))
        for name, val in summaries(q, key):
            body += f"{name:<28s} {val}\n"

        if args.check:
            t = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            bad = "闂" in t or "\ufffd" in t
            print(f"  {str(log.relative_to(REPO)):48s} {'乱码' if bad else '正常'}")
            continue

        # 直接写字节，避免任何文本转码
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(body.encode("utf-8"))
        t = log.read_text(encoding="utf-8")
        ok = "闂" not in t and "\ufffd" not in t
        print(f"  已重建 {logrel:48s} {log.stat().st_size:>6,} B  "
              f"{'✓' if ok else '✗'}")


if __name__ == "__main__":
    main()
