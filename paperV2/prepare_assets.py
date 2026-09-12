"""Prepare manuscript assets from saved results only; never invoke a solver."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCES = {}
CHECKS = []
DATES = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']


def source(rel):
    p = ROOT / rel
    assert '/efficiency/' not in p.as_posix(), p
    SOURCES[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return p


def csv(rel):
    return pd.read_csv(source(rel))


def js(rel):
    return json.loads(source(rel).read_text(encoding='utf-8'))


def esc(v):
    return str(v).replace('&', r'\&').replace('%', r'\%').replace('_', r'\_')


def num(v):
    return f'{float(v):.2f}'


def check(label, a, b, tol=0.02):
    assert np.allclose(a, b, rtol=0, atol=tol), (label, a, b)
    CHECKS.append(label)


def table(caption, headers, rows, label=None, spec=None, size='small'):
    spec = spec or 'l' + 'r'*(len(headers)-1)
    x = [r'\begin{table}[htbp]\centering'+'\\'+size,
         r'\caption{'+caption+'}'+(r'\label{'+label+'}' if label else ''),
         r'\begin{tabular}{'+spec+r'}\toprule',
         ' & '.join(headers)+r'\\\midrule']
    x += [' & '.join(map(str, row))+r'\\' for row in rows]
    x += [r'\bottomrule\end{tabular}\end{table}']
    return '\n'.join(x)+'\n'


def write_table(name, caption, headers, rows, **kwargs):
    (HERE/'tables'/f'{name}.tex').write_text(table(caption, headers, rows, **kwargs), encoding='utf-8')


def grid_table(title, values, daily_g, daily_cost, adjusted=None, adjusted_total=None):
    spans = ['10:00--10:10', '12:00--12:10', '14:00--14:10',
             '16:00--16:10', '18:00--18:10', '20:00--20:10']
    rows = []
    if adjusted is not None:
        rows.append([r'\multicolumn{6}{c}{0点原计划购电量}'])
    for start in (0, 3):
        rows.append(sum(([spans[i], num(values[i])] for i in range(start, start+3)), []))
    rows.append([r'\multicolumn{2}{l}{全天计划购电量}', num(daily_g),
                 r'\multicolumn{2}{l}{全天实际购电费}', num(daily_cost)])
    if adjusted is not None:
        rows.append([r'\multicolumn{6}{c}{最终调整后购电量（不含紧急购电）}'])
        for start in (0, 3):
            rows.append(sum(([spans[i], num(adjusted[i])] for i in range(start, start+3)), []))
        rows.append([r'\multicolumn{5}{l}{全天最终调整后购电量}', num(adjusted_total)])
    return table(title, ['时间段', '购电量']*3, rows, size='scriptsize')


def storage_table(title, charge, discharge, initial, final):
    spans = [f'{h:02}:00--{h+4:02}:00' for h in range(0, 24, 4)]
    rows = []
    for a in range(0, 6, 2):
        rows.append(sum(([spans[i], num(charge[i]), num(discharge[i])] for i in (a, a+1)), []))
    rows.append([r'\multicolumn{2}{l}{0:00储电量}', num(initial),
                 r'\multicolumn{2}{l}{24:00储电量}', num(final)])
    return table(title, ['时间段', '充电量', '放电量']*2, rows, size='scriptsize')


def emergency_table(title, frame):
    groups = [frame.loc[frame.date == d] for d in DATES]
    rows = []
    for i in range(max(map(len, groups))):
        row = []
        for group in groups:
            if i < len(group):
                r = group.iloc[i]
                row += [str(r['span']).replace('—', '--').replace('-', '--') if '—' not in str(r['span']) else str(r['span']).replace('—','--'), num(r.emergency_kwh)]
            else:
                row += ['—', '—']
        rows.append(row)
    rows.append(sum((['合计', num(g.emergency_kwh.sum())] for g in groups), []))
    result = table(title, [r'\multicolumn{2}{c}{'+d[5:]+'}' for d in DATES],
                   [['时间段','电量']*4]+rows, spec='lr'*4, size='scriptsize')
    return result.replace(r'\begin{tabular}', r'\setlength{\tabcolsep}{3pt}\begin{tabular}')


def main():
    for d in ('figures','tables','data','deliverables'):
        (HERE/d).mkdir(exist_ok=True)
    source('data/C题.pdf')
    m = js('paper/figure_package/manifest.json')
    for f in m['figures']:
        for ext in ('pdf','png'):
            rel = 'paper/figure_package/figures/'+f['id']+'.'+ext
            p = source(rel)
            assert hashlib.sha256(p.read_bytes()).hexdigest() == m['output_sha256']['figures/'+p.name]
            shutil.copy2(p, HERE/'figures'/p.name)
        tex = (r'\begin{figure}[htbp]\centering'+'\n'+
               r'\includegraphics[width=\linewidth]{figures/'+f['id']+'.pdf}\n'+
               r'\caption{'+esc(f['caption'])+'}'+r'\label{fig:'+f['id']+'}\n'+
               r'\end{figure}'+'\n')
        (HERE/'figures'/(f['id']+'.tex')).write_text(tex, encoding='utf-8')
    for rel in ('paper/figure_package/图注与正文.md','paper/extra/说明.md','paper/extra/efficiency_robustness.tex'):
        source(rel)
    for q in ('question1','question2','question3','question4/part2','question4/part3'):
        source(q+'/建模说明.md')
        for p in sorted((ROOT/q/'code').glob('*.py')):
            source(p.relative_to(ROOT).as_posix())
    # Shared code is an actual dependency of Q2 and Q4-2, not an alternative model.
    for p in sorted((ROOT/'common/q2_base').glob('*.py')):
        source(p.relative_to(ROOT).as_posix())
    with np.load(source('question1/results/solution.npz')) as z:
        q1 = {k:z[k].copy() for k in z.files}
    baseline = float(np.dot(q1['price'], np.maximum(q1['load']-q1['pv'],0)))
    cost = float(q1['obj_lp'])
    check('Q1 main result',cost,35126.95)
    write_table('q1_summary','典型日储能调度与无储能基线',['方案','购电费/元','较基线节省/元'],
                [['无储能',num(baseline),'—'],['储能主方案',num(cost),num(baseline-cost)]])
    q2=js('question2/results/summary.json')
    old=csv('question2/results/variants/uniform56/daily_summary.csv')
    rows=[]
    for k,label in [('planned_cost_yuan','计划费'),('emergency_cost_yuan','紧急费'),('total_cost_yuan','总费用')]:
        rows.append([label,num(old[k].sum()),num(q2[k])])
    check('Q2 main result',q2['total_cost_yuan'],14389135.08)
    write_table('q2_costs','第二问两种残差口径下的费用（元）',['费用项','含回退残差','有效残差主方案'],rows)
    comps={}
    for q,name in [('question3','q3'),('question4/part3','q43')]:
        c=csv(q+'/results/comparison.csv').set_index('mode')
        comps[name]=c
        labels=[('B_aligned','同口径历史预测'),('only_0','仅0点融合'),('at_0_6','0、6点'),('at_0_6_12','0、6、12点'),('all','四次更新主方案')]
        write_table(name+'_comparison',('第三问' if name=='q3' else '4-3')+'更新频率对照',
                    ['方案','总费用/元','紧急购电量/kWh'],
                    [[label,num(c.loc[k,'total_cost_yuan']),num(c.loc[k,'emergency_kwh'])] for k,label in labels])
        row=c.loc['all']
        keys=[('planned_cost_yuan','原计划费'),('increase_cost_yuan','增购费'),
              ('cancellation_refund_yuan','取消退款（扣减）'),('breach_cost_yuan','违约费'),
              ('adjustment_net_yuan','净调整费'),('emergency_cost_yuan','紧急费'),('total_cost_yuan','总费用')]
        write_table(name+'_costs',('第三问' if name=='q3' else '4-3')+'主结果实际费用分解',
                    ['项目','费用/元'],[[label,num(-row[k] if k=='cancellation_refund_yuan' else row[k])] for k,label in keys])
        check(name+' accounting',row.planned_cost_yuan+row.adjustment_net_yuan+row.emergency_cost_yuan,row.total_cost_yuan)
        c.to_csv(HERE/'data'/(name+'_comparison.csv'),encoding='utf-8-sig')
    q42=csv('question4/part2/results/comparison.csv').set_index('name')
    write_table('q42_comparison','4-2同价结算下的价格信息对照',
                ['方案','实际费用/元','较重结算基线节省/元'],
                [[label,num(q42.loc[k,'total_cost_yuan']),num(q42.loc[k,'saving_vs_repriced_q2_yuan'])] for k,label in
                 [('q2_repriced','原Q2计划重结算'),('mean_price','均价对照'),('joint_price','联合场景主方案'),('known_today_price','当日电价已知对照')]])
    q42.to_csv(HERE/'data/q42_comparison.csv',encoding='utf-8-sig')
    # Use only the authorized extra document for alternative-efficiency numbers.
    eff=source('paper/extra/efficiency_robustness.tex').read_text(encoding='utf-8')
    matches=re.findall(r'(问题[一二三]|问题四-[23])\s*&\s*([\d.]+)\s*&\s*([\d.]+)\s*&\s*(-[\d.]+)\s*&\s*\$(-[\d.]+)',eff)
    assert len(matches)==5
    main_values=[cost,q2['total_cost_yuan'],comps['q3'].loc['all','total_cost_yuan'],q42.loc['joint_price','total_cost_yuan'],comps['q43'].loc['all','total_cost_yuan']]
    for r,v in zip(matches,main_values):
        check('efficiency primary '+r[0],float(r[1]),v)
        check('efficiency difference '+r[0],float(r[2])-float(r[1]),float(r[3]))
    write_table('efficiency','已有两种效率口径总费用对照（元）',
                ['结果集','往返0.81','往返0.90','差额','变化率'],
                [[*r[:4],r[4]+r'\%'] for r in matches],label='tab:efficiency',size='small')
    pd.DataFrame(matches,columns=['result','main_yuan','alternative_yuan','difference_yuan','percent']).to_csv(HERE/'data/efficiency_transcribed.csv',index=False,encoding='utf-8-sig')
    # Required table 1/2 layouts and complete continuous emergency intervals.
    out=[r'\subsection{问题一指定结果}']
    selected=[60,72,84,96,108,120]
    out.append(grid_table('问题一：指定时段及全天购电',q1['g'][selected],q1['g'].sum(),cost))
    out.append(storage_table('问题一：四小时充放电与首末储电量',q1['c'].reshape(6,24).sum(1),q1['d'].reshape(6,24).sum(1),6000,6000))
    out.append(r'\FloatBarrier')
    n_emergency=0
    for q,label in [('question2','问题二'),('question3','问题三'),('question4/part2','4-2'),('question4/part3','4-3')]:
        out.append(r'\subsection{'+label+'指定日期结果}')
        if q.endswith('part2'):
            paths=['target_days/table1_grid.csv','target_days/table2_storage.csv','target_days/table3_emergency.csv','target_days/daily_summary.csv']
        else:
            paths=['target_table1.csv','target_table2.csv','target_table3.csv','target_daily.csv']
        t1,t2,t3,ds=[csv(q+'/results/'+p) for p in paths]
        t1=t1.rename(columns={'interval':'span','planned_grid_kwh':'planned_kwh'})
        t2=t2.rename(columns={'interval':'span'})
        t3=t3.rename(columns={'interval':'span'})
        for key,frame in [('grid',t1),('storage',t2),('emergency',t3),('daily',ds)]:
            frame.to_csv(HERE/'data'/(q.replace('/','_')+'_'+key+'.csv'),index=False,encoding='utf-8-sig')
        for date in DATES:
            a=t1.loc[t1.date==date].head(6)
            b=t2.loc[(t2.date==date)&t2.discharge_kwh.notna()].head(6)
            d=ds.loc[ds.date==date].iloc[0]
            assert len(a)==len(b)==6
            adjusted='adjusted_kwh' in a
            planned=a['original_kwh' if adjusted else 'planned_kwh'].to_numpy()
            total=d['original_kwh' if adjusted else ('planned_kwh_day' if 'planned_kwh_day' in d else 'g_kwh')]
            out.append(grid_table(label+' '+date+'：指定时段及全天购电',planned,total,d.total_cost_yuan,
                                  a.adjusted_kwh.to_numpy() if adjusted else None,
                                  d.adjusted_kwh if adjusted else None))
            initial=d['energy_00' if 'energy_00' in d else 'energy_start_kwh']
            final=d['energy_24' if 'energy_24' in d else 'energy_end_kwh']
            out.append(storage_table(label+' '+date+'：四小时充放电与首末储电量',b.charge_kwh.to_numpy(),b.discharge_kwh.to_numpy(),initial,final))
            check(label+' '+date+' energy',initial+.9*b.charge_kwh.sum()-b.discharge_kwh.sum()/.9,final)
            check(label+' '+date+' emergency',t3.loc[t3.date==date,'emergency_kwh'].sum(),d['emergency_kwh_day' if 'emergency_kwh_day' in d else 'emergency_kwh'])
            out.append(r'\FloatBarrier')
        out.append(emergency_table(label+'：指定日期全部紧急购电区间',t3))
        out.append(r'\FloatBarrier')
        n_emergency+=len(t3)
    (HERE/'tables/target_results.tex').write_text('\n'.join(out)+'\n',encoding='utf-8')
    for q,file in [('question1','result1.xlsx'),('question2','result2.xlsx'),('question3','result3.xlsx'),('question4/part2','result4-2.xlsx'),('question4/part3','result4-3.xlsx')]:
        shutil.copy2(source(q+'/results/'+file),HERE/'deliverables'/file)
    for q in ('question2','question3','question4/part2','question4/part3'):
        source(q+'/results/verification.json')
    for rel,h in SOURCES.items():
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==h
    outputs={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
             for folder in ('figures','tables','data','deliverables') for p in sorted((HERE/folder).glob('*')) if p.is_file()}
    manifest={'source_sha256':SOURCES,'output_sha256':outputs,'checks':CHECKS,
              'figures':10,'required_dates':DATES,'complete_emergency_rows':n_emergency,
              'scope':'No optimization rerun. Efficiency alternative numbers transcribed only from paper/extra. Q4-3 objective discrepancy disclosed.'}
    (HERE/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Prepared 10 figures, five unchanged workbooks, {n_emergency} emergency intervals; {len(CHECKS)} arithmetic checks passed.')


if __name__=='__main__':
    main()
