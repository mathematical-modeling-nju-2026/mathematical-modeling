"""Run Q3 and comparable ablations. Outputs stay in this directory.

python run_q3.py                     # full-year solution and all comparisons
python run_q3.py --mode all --days 4 --out smoke
"""
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import json
import os
import platform
import time
import numpy as np
import pandas as pd
from q3_data import HERE, T, load_data, label, intervals
from q3_forecast import Forecaster
from q3_model import solve, E_INIT

# 附件5 result4-3.xlsx 模板（用于取原表头，保证导出与模板逐列一致）
_ETA_DIR = Path(__file__).resolve().parents[3] / "common" / "efficiency"
if str(_ETA_DIR) not in sys.path:
    sys.path.insert(0, str(_ETA_DIR))
from template_layout import TPL43 as TPL  # noqa: E402

MODES = {
    'B_aligned': ('history', (0,)),
    'only_0': ('fusion', (0,)),
    'at_0_6': ('fusion', (0, 1)),
    'at_0_6_12': ('fusion', (0, 1, 2)),
    'all': ('fusion', (0, 1, 2, 3)),
}


def simulate(f, mode, end=365):
    source, stages = MODES[mode]
    energy = E_INIT
    records, daily, trees = [], [], {}
    started = time.time()
    for day in range(31, end):
        price = f.data['price_rt'][day]
        date = (datetime(2025, 1, 1) + timedelta(days=day)).strftime('%Y-%m-%d')
        day_start = energy
        original = None
        q = np.zeros(T); c = np.zeros(T); d = np.zeros(T); E = np.zeros(T)
        issues = np.zeros(T, dtype=int); forecast = np.zeros(T)
        worst_eq = worst_ineq = 0.
        max_nodes = 0
        overlap = 0
        for stage in stages:
            r = solve(f, day, stage, stages, energy, day_start, original, source)
            original = r['original']
            start, stop = stage * 36, r['stop']
            q[start:stop], c[start:stop], d[start:stop], E[start:stop] = r['q'], r['c'], r['d'], r['E']
            energy = E[stop - 1]
            issues[start:stop] = stage * 6
            forecast[start:stop] = f.point(day, stage, source)[start:stop]
            worst_eq = max(worst_eq, r['lp_eq_max'])
            worst_ineq = max(worst_ineq, r['lp_ineq_max'])
            max_nodes = max(max_nodes, r['nodes'])
            overlap += r['raw_overlap']
            if day in (31, 78, 171, 265, 354) and stage == 0:
                trees[date] = r['tree']
        actual = (f.data['load'][day] - f.data['pv'][day]) / 6
        z = q + d - c
        emergency = np.maximum(actual - z, 0)
        dumped = np.maximum(z - actual, 0)
        up, down = np.maximum(q - original, 0), np.maximum(original - q, 0)
        planned_cost = price * original
        added_cost, cancellation_refund, breach_cost = 1.5 * price * up, price * down, .5 * price * down
        adjustment_cost = added_cost - cancellation_refund + breach_cost
        emergency_cost = 5 * price * emergency
        total = planned_cost + adjustment_cost + emergency_cost
        before = np.r_[day_start, E[:-1]]
        for t in range(T):
            records.append(dict(date=date, slot=t, start=label(t), end=label(t + 1),
                                issue_hour=int(issues[t]), price_yuan_per_kwh=price[t],
                                original_kwh=original[t], adjusted_kwh=q[t], increase_kwh=up[t], decrease_kwh=down[t],
                                charge_kwh=c[t], discharge_kwh=d[t], energy_before_kwh=before[t], energy_after_kwh=E[t],
                                load_kwh=f.data['load'][day,t]/6, pv_kwh=f.data['pv'][day,t]/6,
                                forecast_net_kwh=forecast[t], net_supply_kwh=z[t], emergency_kwh=emergency[t], dump_kwh=dumped[t],
                                planned_cost_yuan=planned_cost[t], increase_cost_yuan=added_cost[t],
                                cancellation_refund_yuan=cancellation_refund[t], breach_cost_yuan=breach_cost[t],
                                adjustment_net_yuan=adjustment_cost[t], emergency_cost_yuan=emergency_cost[t], total_cost_yuan=total[t]))
        daily.append(dict(date=date, planned_cost_yuan=planned_cost.sum(), increase_cost_yuan=added_cost.sum(),
                          cancellation_refund_yuan=cancellation_refund.sum(), breach_cost_yuan=breach_cost.sum(),
                          adjustment_net_yuan=adjustment_cost.sum(), emergency_cost_yuan=emergency_cost.sum(),
                          total_cost_yuan=total.sum(), original_kwh=original.sum(), adjusted_kwh=q.sum(),
                          increase_kwh=up.sum(), decrease_kwh=down.sum(), emergency_kwh=emergency.sum(),
                          dump_kwh=dumped.sum(), charge_kwh=c.sum(), discharge_kwh=d.sum(),
                          energy_start_kwh=day_start, energy_end_kwh=energy,
                          lp_eq_max=worst_eq, lp_ineq_max=worst_ineq, max_tree_nodes=max_nodes,
                          raw_simultaneous_slots=overlap))
        if (day - 31) % 30 == 0 or day == end - 1:
            print(f'{mode:12s} {date} cost={sum(x["total_cost_yuan"] for x in daily)/1e4:.2f} wan; {time.time()-started:.1f}s', flush=True)
    detail, days = pd.DataFrame(records), pd.DataFrame(daily)
    sums = days.select_dtypes(include='number').sum().to_dict()
    summary = {k:float(sums[k]) for k in ('planned_cost_yuan','increase_cost_yuan','cancellation_refund_yuan',
               'breach_cost_yuan','adjustment_net_yuan','emergency_cost_yuan','total_cost_yuan',
               'original_kwh','adjusted_kwh','increase_kwh','decrease_kwh','emergency_kwh','dump_kwh')}
    summary.update(mode=mode, source=source, update_hours=[s*6 for s in stages], days=len(days),
                   initial_energy_kwh=float(days.iloc[0].energy_start_kwh),
                   final_energy_kwh=float(days.iloc[-1].energy_end_kwh), seconds=time.time()-started)
    return detail, days, summary, trees


def export_excel(detail, days, path):
    import openpyxl
    from openpyxl.styles import Font, Alignment
    from openpyxl.comments import Comment
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                            / "common" / "efficiency"))
    from template_layout import block_labels, circular, template_labels
    book = openpyxl.Workbook()
    book.remove(book.active)
    # 模板表头（左端点，首格 0:10-0:20）+ 环形映射 out[i]=data[(i+1)%144]
    headers = template_labels(TPL, '计划购电量')
    blocks6 = block_labels(TPL, '充放电量')
    for name, col, cost in [('计划购电量','original_kwh','planned_cost_yuan'),
                            ('调整购电量','adjusted_kwh','adjustment_net_yuan')]:
        ws = book.create_sheet(name)
        ws.append(['日期\\时间']+headers+['全天购电量','全天购电费'])
        if col == 'adjusted_kwh':
            ws.cell(1,147).comment = Comment('此列为相对0点计划的净调整费用：1.5p×增购−0.5p×减购；表内购电量为调整后总量。', 'Q4-3')
        for date, group in detail.groupby('date',sort=False):
            row = days.loc[days.date == date].iloc[0]
            vals = circular(group[col].to_numpy(float))
            ws.append([datetime.fromisoformat(date)]+[round(v,6) for v in vals]
                      +[group[col].sum(),float(row[cost])])
        ws.freeze_panes='B2'
        ws.column_dimensions['A'].width=13
    ws=book.create_sheet('充放电量')
    ws.append(['日期','时间段','充电量','放电量','时刻','储电量'])
    for date, group in detail.groupby('date',sort=False):
        for b in range(6):
            g=group.iloc[b*24:(b+1)*24]
            ws.append([datetime.fromisoformat(date) if b==0 else None,
                       blocks6[b],g.charge_kwh.sum(),g.discharge_kwh.sum(),
                       '0:00' if b==0 else ('24:00' if b==1 else None),
                       group.iloc[0].energy_before_kwh if b==0 else (group.iloc[-1].energy_after_kwh if b==1 else None)])
    ws=book.create_sheet('紧急购电量')
    ws.append(['日期','购电时间段','购电量'])
    for date, group in detail.groupby('date',sort=False):
        blocks=list(intervals(group.emergency_kwh.to_numpy())) or [('—',0.)]
        for i,(span,amount) in enumerate(blocks):
            ws.append([datetime.fromisoformat(date) if i==0 else None,span,amount])
    for ws in book:
        for cell in ws[1]:
            cell.font=Font(bold=True); cell.alignment=Alignment(horizontal='center')
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value,datetime): cell.number_format='yyyy-mm-dd'
                elif isinstance(cell.value,(float,int)): cell.number_format='0.0000'
        if ws.max_column<10:
            for col in 'ABCDEF': ws.column_dimensions[col].width=18
    book.save(path)


def target_tables(detail, days, out):
    targets=['2025-03-20','2025-06-21','2025-09-23','2025-12-21']
    rows1, rows2, rows3=[],[],[]
    for date in targets:
        g=detail[detail.date==date]
        if not len(g): continue
        for hour in (10,12,14,16,18,20):
            r=g.iloc[hour*6]
            rows1.append(dict(date=date,span=r['start']+'-'+r['end'],original_kwh=r.original_kwh,adjusted_kwh=r.adjusted_kwh))
        for b in range(6):
            block=g.iloc[b*24:(b+1)*24]
            rows2.append(dict(date=date,span=label(b*24)+'-'+label((b+1)*24),charge_kwh=block.charge_kwh.sum(),discharge_kwh=block.discharge_kwh.sum()))
        for span,amount in intervals(g.emergency_kwh.to_numpy()): rows3.append(dict(date=date,span=span,emergency_kwh=amount))
    pd.DataFrame(rows1).to_csv(out/'target_table1.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(rows2).to_csv(out/'target_table2.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(rows3).to_csv(out/'target_table3.csv',index=False,encoding='utf-8-sig')
    days[days.date.isin(targets)].to_csv(out/'target_daily.csv',index=False,encoding='utf-8-sig')


def write_report(out):
    """Keep the readable result notes tied to the actual exported numbers."""
    comp=pd.read_csv(out/'comparison.csv')
    report_days=int(comp.iloc[0]['days'])
    last_date=(datetime(2025,2,1)+timedelta(days=report_days-1)).strftime('%Y年%m月%d日')
    model_doc=Path(os.path.relpath(HERE.parent/'建模说明.md',out)).as_posix()
    names={'B_aligned':'方案B框架同口径复算','only_0':'仅使用0点融合预报',
           'at_0_6':'0、6点','at_0_6_12':'0、6、12点','all':'0、6、12、18点（主方案）'}
    lines=['# 第三问结果说明','',
           f'结果期为2025年2月1日至{last_date}，共{report_days}天。采用在线预报融合、经验场景树LP和跨日滚动执行；详见 [建模说明.md]({model_doc})。',
           '', '**费用口径**：取消部分退原费、另付50%违约费；费用按供电时段电价计算。原计划费、增购费、退款、违约费、紧急费分开记账。',
           '', '## 全年对照','',
           '| 方案 | 总费用（元） | 紧急购电量（kWh） |','|---|---:|---:|']
    for _,r in comp.iterrows():
        lines.append(f'| {names[r["mode"]]} | {r.total_cost_yuan:,.2f} | {r.emergency_kwh:,.2f} |')
    idx=comp.set_index('mode')
    if 'all' in idx.index:
        a=idx.loc['all']
        lines+=['','## 主方案费用分解','',
                '| 项目 | 金额（元） |','|---|---:|',
                f'| 原计划购电费 | {a.planned_cost_yuan:,.2f} |',
                f'| 增购费（1.5倍） | {a.increase_cost_yuan:,.2f} |',
                f'| 取消原费退款 | −{a.cancellation_refund_yuan:,.2f} |',
                f'| 取消违约费（50%） | {a.breach_cost_yuan:,.2f} |',
                f'| 净调整费 | {a.adjustment_net_yuan:,.2f} |',
                f'| 紧急购电费（5倍） | {a.emergency_cost_yuan:,.2f} |',
                f'| **总费用** | **{a.total_cost_yuan:,.2f}** |','',
                '净调整费已经包含增购费、退款和违约费，计算总额时不能重复叠加这三项。']
        if 'B_aligned' in idx.index:
            b=idx.loc['B_aligned']
            lines += ['',f'相对同口径方案B，主方案节省 **{b.total_cost_yuan-a.total_cost_yuan:,.2f}元（{(1-a.total_cost_yuan/b.total_cost_yuan)*100:.2f}%）**；紧急购电量减少 **{(1-a.emergency_kwh/b.emergency_kwh)*100:.2f}%**。',
                      '', '## 是否需要每次都调整','']
        for old,new in [('B_aligned','only_0'),('only_0','at_0_6'),('at_0_6','at_0_6_12')]:
            if old in idx.index and new in idx.index:
                delta=idx.loc[old].total_cost_yuan-idx.loc[new].total_cost_yuan
                lines.append(f'- 从“{names[old]}”改为“{names[new]}”，全年减少费用 {delta:,.2f} 元。')
        if 'at_0_6_12' in idx.index:
            delta=a.total_cost_yuan-idx.loc['at_0_6_12'].total_cost_yuan
            lines += ['',f'加入18点更新后，全年费用变化为 **{delta:+,.2f}元**。此差值很小，数据未显示18点更新有明确的额外经济收益。建议重点保留6点和12点调整；18点可以作为可选更新。',
                      '', '该结论限于本数据和算法：18点仍可能通过次日预报影响跨日储能，不能断言其永远无用。小型经验树重新聚类、滚动重算、有限样本和真实误差会使回测费用并非严格随信息增多而下降。',
                      '', '主结果 [result3.xlsx](result3.xlsx) 保留预设的四次更新方案；[0、6、12点结果](comparisons/at_0_6_12/result3.xlsx) 单独提供。上述更新频率比较属于本年度数据上的方案分析。']
    if (out/'target_daily.csv').exists():
        target=pd.read_csv(out/'target_daily.csv')
        lines += ['','## 题目指定日期','',
                  '| 日期 | 原计划费（元） | 净调整费（元） | 紧急电量（kWh） | 紧急费（元） | 总费用（元） | 0点/24点储电量（kWh） |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for _,r in target.iterrows():
            lines.append(f'| {r.date} | {r.planned_cost_yuan:,.2f} | {r.adjustment_net_yuan:,.2f} | {r.emergency_kwh:,.2f} | {r.emergency_cost_yuan:,.2f} | {r.total_cost_yuan:,.2f} | {r.energy_start_kwh:,.2f} / {r.energy_end_kwh:,.2f} |')
        lines += ['', '表1的指定十分钟购电量、表2的六个四小时充放电量、表3的全部紧急时间区间，分别保存在 `target_table1.csv`、`target_table2.csv`、`target_table3.csv`；日汇总及首末SOC保存在 `target_daily.csv`。']
    lines += ['','## 核验与解释边界','',
              '- 主方案及对照的初末SOC统一为6000 kWh，能量递推、上下限、功率、充放电互斥、跨日连续和实际缺口均逐段核验。具体误差见 `verification.json`。',
              '- `verify_q3.py` 另对三天四个发布时刻做未来信息扰动，反读Excel并独立核算费用；应以该脚本更新后的 `verification.json` 为完整检查记录。',
              '- 方案B的历史内核参数由既有方案继承，不能据本次因果执行检查声称原参数选择过程一定没有用过测试数据。',
              '- 取消量若不退还原费，同一主调度的费用会增加退款总额；该敏感性写入核验JSON。若更换结算解释，应重新优化，不能只换最终报表公式。',
              '- 主方案为有限经验场景上的LP加滚动执行，不宣称全年真实随机问题全局最优。',
              '', '## 图表','',
              '![费用与紧急电量对照](figures/cost_comparison.png)','',
              '![四个指定日购电与储能](figures/target_dispatch.png)','',
              '![发布预报与历史信息融合](figures/forecast_fusion.png)','']
    (out/'结果说明.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=list(MODES)+['suite'],default='suite')
    ap.add_argument('--days',type=int,default=334)
    ap.add_argument('--out',type=Path,default=HERE)
    args=ap.parse_args()
    out=args.out if args.out.is_absolute() else HERE/args.out
    out.mkdir(parents=True,exist_ok=True)
    data=load_data(); f=Forecaster(data)
    end=min(365,31+args.days)
    summaries=[]
    modes=MODES if args.mode=='suite' else [args.mode]
    for mode in modes:
        detail,days,summary,trees=simulate(f,mode,end)
        dest=out if mode=='all' else out/'comparisons'/mode
        dest.mkdir(parents=True,exist_ok=True)
        detail.to_csv(dest/'schedule_detail.csv',index=False,encoding='utf-8-sig')
        days.to_csv(dest/'daily_summary.csv',index=False,encoding='utf-8-sig')
        (dest/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        summaries.append(summary)
        from verify_q3 import check_schedule
        checks=check_schedule(detail,days,data,require_year_end=end==365)
        (dest/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
        if not checks['pass']: raise RuntimeError(f'Independent verification failed: {mode}')
        if mode=='at_0_6_12':
            # A ready-to-review lower-frequency alternative, kept separate from the preset main policy.
            export_excel(detail,days,dest/'result4-3.xlsx')
        if mode=='all':
            export_excel(detail,days,out/'result4-3.xlsx')
            target_tables(detail,days,out)
            (out/'scenario_trees.json').write_text(json.dumps(trees,ensure_ascii=False,indent=2),encoding='utf-8')
    pd.DataFrame(summaries).to_csv(out/'comparison.csv',index=False,encoding='utf-8-sig')
    f.diagnostics(end=end).to_csv(out/'forecast_diagnostics.csv',index=False,encoding='utf-8-sig')
    import scipy
    metadata=dict(source_sha256=data['source_sha256'],python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,
                  residual_window_days=56,first_residual_day='2025-01-08',history_load='sw4/drift5',history_pv='t7/drift28',
                  initialization='January battery idle at 6000 kWh; all reports start February 1 at 6000',
                  end_condition='48h end equals current day start; Dec 31 ends at 6000',
                  settlement='attachment-4 actual real-time price p: p*g0 + 1.5*p*max(q-g0,0) - 0.5*p*max(g0-q,0) + 5*p*emergency',
                  execution='Only next issue block is committed; each delivery slot adjusted at most once.',
                  method='Joint historical net-load and real-time-price scenario LP; causal seven-day price forecast plus residual scenarios; deterministic next-day tail; receding-horizon execution.')
    (out/'run_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    write_report(out)
    print(pd.DataFrame(summaries)[['mode','total_cost_yuan','emergency_kwh']].to_string(index=False))


if __name__=='__main__': main()
