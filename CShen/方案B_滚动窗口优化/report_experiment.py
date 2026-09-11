"""Publish the structural warm-up fix; report all window attempts, including losses."""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
import pandas as pd
from rolling_window import HERE, SOURCE

LABELS={
    'uniform56':'56天等权','half_life7':'56天/半衰期7天','half_life14':'56天/半衰期14天',
    'half_life28':'56天/半衰期28天','online_primary':'四候选每周选择',
    'uniform28':'28天等权','uniform42':'42天等权','online_extended':'六候选每周选择'}


def collect():
    groups=[('原样本口径',HERE),('短窗口扩展',HERE/'extensions'/'short_windows'),
            ('排除回退残差',HERE/'sensitivity'/'valid_residuals')]
    rows=[]
    for group,folder in groups:
        x=pd.read_csv(folder/'comparison.csv')
        x['group']=group
        x['relative_folder']=[str((folder/'variants'/name).relative_to(HERE)).replace('\\','/') for name in x.name]
        rows.append(x)
    df=pd.concat(rows,ignore_index=True)
    baseline=float(df.loc[(df.group=='原样本口径')&(df.name=='uniform56'),'total_cost_yuan'].iloc[0])
    df['saving_vs_original_yuan']=baseline-df.total_cost_yuan
    df.to_csv(HERE/'all_comparisons.csv',index=False,encoding='utf-8-sig')
    return df,baseline


def main():
    roots={'primary':HERE,'valid_residuals':HERE/'sensitivity'/'valid_residuals',
           'short_windows':HERE/'extensions'/'short_windows'}
    bundle={key:json.loads((folder/'verification.json').read_text(encoding='utf-8')) for key,folder in roots.items()}
    bundle['information']=json.loads((HERE/'information_verification.json').read_text(encoding='utf-8'))
    if not all(bundle[key].get('pass') is True for key in roots) or bundle['information'].get('pass_check') is not True:
        raise RuntimeError('All schedule, workbook and information checks must pass before publication')
    df,baseline=collect()
    old=json.loads((SOURCE.parent/'summary.json').read_text(encoding='utf-8'))
    old_gap=abs(baseline-old['total_cost_yuan'])
    if old_gap>1e-6:raise RuntimeError('Original baseline was not exactly reproduced')
    recommended=HERE/'sensitivity'/'valid_residuals'/'variants'/'uniform56'
    base_days=pd.read_csv(HERE/'variants'/'uniform56'/'daily_summary.csv')
    recommended_days=pd.read_csv(recommended/'daily_summary.csv')
    if not base_days.date.equals(recommended_days.date):
        raise RuntimeError('Comparison dates do not match')
    cost_difference=base_days.total_cost_yuan-recommended_days.total_cost_yuan
    changed_dates=base_days.loc[cost_difference.abs()>1e-6,'date']
    # This choice follows the first valid weekday forecast, not a tuned numeric cutoff.
    for name in ('result2.xlsx','daily_summary.csv','schedule_detail.csv.gz'):
        shutil.copy2(recommended/name,HERE/name)
    summary=json.loads((recommended/'summary.json').read_text(encoding='utf-8'))
    summary.update(recommended_variant='sensitivity/valid_residuals/variants/uniform56',
                   recommendation_reason='Use only genuine historical weekday forecasts: skip Jan1-7 fallback residuals; keep original 56-day equal weights.',
                   baseline_total_cost_yuan=baseline,saving_yuan=baseline-summary['total_cost_yuan'],
                   saving_percent=(1-summary['total_cost_yuan']/baseline)*100,
                   evaluation_start=str(base_days.date.iloc[0]),evaluation_end=str(base_days.date.iloc[-1]),
                   cost_difference_last_date=str(changed_dates.iloc[-1]) if len(changed_dates) else None,
                   weighted_window_conclusion='No robust improvement after controlling early fallback residuals.')
    (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    bundle['original_cost_reproduction_error']=old_gap
    bundle['published_file_hashes']={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                                     for name in ('result2.xlsx','daily_summary.csv','schedule_detail.csv.gz')}
    bundle['published_files_identical_to_verified_variant']=all((HERE/n).read_bytes()==(recommended/n).read_bytes() for n in bundle['published_file_hashes'])
    bundle['pass']=bundle['published_files_identical_to_verified_variant'] and old_gap<=1e-6
    if not bundle['pass']:raise RuntimeError('Published files differ from the verified variant')
    (HERE/'verification_all.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
    repo=SOURCE.parents[2]
    dependencies=[SOURCE,repo/'C_yang'/'q2'/'q2_data.py']
    dependencies += [repo/'C_yang'/'raw'/'附件'/f'附件{i}.xlsx' for i in (1,2)]
    (HERE/'source_fingerprints.json').write_text(json.dumps({str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},ensure_ascii=False,indent=2),encoding='utf-8')
    # Expose contributions month by month, rather than only showing a winning total.
    monthly=[]
    for _,r in df.iterrows():
        daily=pd.read_csv(HERE/r.relative_folder/'daily_summary.csv')
        m=pd.DataFrame({'month':pd.to_datetime(daily.date).dt.month,
                        'saving_yuan':base_days.total_cost_yuan-daily.total_cost_yuan})
        for month,row in m.groupby('month').sum().iterrows():
            monthly.append(dict(group=r.group,name=r['name'],month=month,saving_yuan=row.saving_yuan))
    pd.DataFrame(monthly).to_csv(HERE/'monthly_savings.csv',index=False,encoding='utf-8-sig')
    clean=df[df.group=='排除回退残差'].set_index('name')
    primary=df[df.group=='原样本口径'].set_index('name')
    best_weight=primary.loc['half_life28']
    clean_base=clean.loc['uniform56']
    f28=pd.read_csv(HERE/'variants'/'half_life28'/'daily_summary.csv')
    feb=(pd.to_datetime(base_days.date).dt.month==2)
    feb_gain=float((base_days.total_cost_yuan-f28.total_cost_yuan)[feb].sum())
    recommended_feb_gain=float(cost_difference[feb].sum())
    recommended_march_gain=float(cost_difference[pd.to_datetime(base_days.date).dt.month==3].sum())
    lines=['# 方案B滚动窗口优化结果','',
           '**结论：近期加权和缩短窗口没有显示稳定的额外收益；本轮推荐修正有效残差筛选，保留原56天等权及48小时前瞻。**','',
           f'原目录基线已精确复现：**{baseline:,.2f}元**。推荐方案为 **{summary["total_cost_yuan"]:,.2f}元**，减少 **{summary["saving_yuan"]:,.2f}元（{summary["saving_percent"]:.4f}%）**。这个收益归因于排除回退预测残差，不归因于指数加权。','',
           '**费用统计期为2025年2月1日至12月31日，共334天；1月仅作共同预热，不计入下表费用。** 所有方案共享原等权1月预热，2月1日SOC为8550 kWh，12月31日为6000 kWh。原目录名“1439万”不是当前保存结果的精确值；这里统一与目录中1440.20万元结果比较。','',
           '## 1. 保持原样本口径的窗口实验','',
           '| 方法 | 2—12月费用（元） | 较原基线节省（元，负数为变差） | 紧急电量（kWh） |','|---|---:|---:|---:|']
    for _,r in df[df.group!='排除回退残差'].iterrows():
        lines.append(f'| {LABELS[r["name"]]} | {r.total_cost_yuan:,.2f} | {r.saving_vs_original_yuan:+,.2f} | {r.emergency_kwh:,.2f} |')
    lines += ['',f'28天半衰期在统计期内减少 {best_weight.saving_vs_original_yuan:,.2f} 元，其中2月减少 {feb_gain:,.2f} 元，3—12月合计反而增加 {feb_gain-best_weight.saving_vs_original_yuan:,.2f} 元。其下半年费用比原等权增加 {best_weight.h2_cost_yuan-primary.loc["uniform56"].h2_cost_yuan:,.2f} 元。',
              '', '固定候选的年度回测最佳属于回顾性比较，不能直接称为严格独立测试后的最优参数。两种每周选择方案均只使用此前已实现的预测损失，未使用当天或未来实际值。',
              '', '## 2. 为什么要修正有效残差','',
              '原负载预测器在1月1—7日没有同星期几历史，使用附件1典型日回退；1月8日起才具有至少一次同星期几历史。原 residual_matrix 把前7天回退预测的误差也算作正常残差。文档声称的“预热残差为NaN”未落实到代码。',
              '', '前7天残差是合法的因果预测误差，并非数值或计算错误。这里的“有效残差”指由具有同星期历史的预测器产生、与后续运行口径更一致的误差；是否适合剔除，要通过对照检验判断。',
              '', '因此采用由预测器可用性决定的边界：场景历史仅取 day >= 7（1月8日起），而非通过遍历全年费用挑选截断日。预测器、效率、功率、前瞻和原始数据均保留。2月1日使用24条有效残差，之后增至最多56条。',
              '', '## 3. 排除前7天回退残差后的配对检验','',
              '| 方法 | 总费用（元） | 较有效残差等权基线增加（元） |','|---|---:|---:|']
    for name,r in clean.iterrows():
        lines.append(f'| {LABELS[name]} | {r.total_cost_yuan:,.2f} | {r.total_cost_yuan-clean_base.total_cost_yuan:+,.2f} |')
    lines += ['', '在这组更一致的历史误差口径下，加权与四候选在线选择都没有优于等权。因此最终交付采用“有效残差 + 56天等权”，不把第一组中偏向近期的表面收益解释为普遍有效。',
              '', '## 4. 推荐结果与变化解释','',
              '| 项目 | 原方案（元） | 推荐方案（元） |','|---|---:|---:|',
              f'| 计划购电费 | {primary.loc["uniform56"].planned_cost_yuan:,.2f} | {summary["planned_cost_yuan"]:,.2f} |',
              f'| 紧急购电费 | {primary.loc["uniform56"].emergency_cost_yuan:,.2f} | {summary["emergency_cost_yuan"]:,.2f} |',
              f'| 总费用 | {baseline:,.2f} | {summary["total_cost_yuan"]:,.2f} |','',
              '排除来自回退预测、与正常预测器口径不同的早期残差后，计划购电费用下降。紧急购电有所增加，但计划费减少更多，所以总费用下降。该模型的目标始终是总费用，不是紧急电量单独最小。',
              '', f'**这是启动阶段的改善。** 2月节省 {recommended_feb_gain:,.2f} 元，3月增加 {-recommended_march_gain:,.2f} 元；最后一个费用有差异的日期为 {summary["cost_difference_last_date"]}，3月5日至12月31日逐日费用与原方案一致。这不能解释为全年持续适应能力的提高。',
              '', '可使用根目录 [result2.xlsx](result2.xlsx)、[daily_summary.csv](daily_summary.csv)、`schedule_detail.csv.gz`。它们与已独立核验的有效残差等权方案逐字节一致；[summary.json](summary.json)记录来源。原方案文件没有修改，第三问没有重算。',
              '', '## 5. 已完成核验','',
              '- 11组完整统计期方案均逐段复算48,096个时段，并反读各自Excel三表；检查能量守恒、效率、功率、SOC、互斥、跨日、初末、电价、实际净负载、缺口和总费用。',
              '- 基线费用与原目录汇总一致；分时充放电导出按24段/4小时，表头按真实00:00—00:10起始时段修正。',
              '- 在2月1日、6月1日、11月30日修改当天及未来负载/光伏，重建预测、残差、评分及LP后，当前选择和控制量均不变；周内后来发生的误差不会反向改变已选窗口。',
              '- 两组有解析解的加权LP费用分别为34,200与57,600元，与求解器一致。人工注入SOC、电价、缺口、时段和Excel错误能被核验器拒绝。',
              '- 核验范围见 `verification_all.json`、三个实验根目录的 `verification.json` 及 `information_verification.json`。',
              '', '## 6. 结论边界','',
              '这里检验的是继承方案B参数后的滚动执行与窗口规则。原预测参数当初如何选择仍依赖其研发记录；本次未来扰动检查不能证明原参数选择没有使用过测试年信息。此次结果也不证明56天对其他年份最优。',
              '', '截断日依据预测器可用性确定，但推荐方案的费用改善来自同一年度回测，尚未经过另一个年份的独立验证。',
              '', '原方案中光伏点预测可能为负、1月预热使用附件1回退等其他口径保持不变，未把这些独立问题混入本次收益。次日仍只用点预测，未延长前瞻，也未开放日内重新调度。',
              '', '![费用差异与收益发生时间](figures/window_comparison.png)','']
    (HERE/'结果说明.md').write_text('\n'.join(lines),encoding='utf-8')
    make_plot(df,baseline,base_days)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def make_plot(df,baseline,base_days):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    fonts={f.name for f in font_manager.fontManager.ttflist}
    family=next((n for n in ['Microsoft YaHei','SimHei','Noto Sans CJK SC'] if n in fonts),'DejaVu Sans')
    plt.rcParams.update({'font.family':family,'axes.unicode_minus':False,'font.size':10,'pdf.fonttype':42,
                         'axes.spines.top':False,'axes.spines.right':False})
    plot=df[df.group!='排除回退残差'].copy()
    fig,axes=plt.subplots(1,2,figsize=(12.5,4.5),layout='constrained')
    vals=plot.saving_vs_original_yuan/1e4
    bars=axes[0].barh([LABELS[n] for n in plot.name],vals,color=['#3B8595' if v>=0 else '#D99951' for v in vals])
    axes[0].bar_label(bars,fmt='%+.2f',padding=4,fontsize=8)
    axes[0].axvline(0,color='#777777',lw=.8)
    axes[0].set(xlabel='较原方案节省（万元；负数为变差）',title='加权程度过高会增加费用',xlim=(min(vals)-.8,max(vals)+.8))
    axes[0].invert_yaxis()
    for folder,name,color in [
        (HERE/'variants'/'half_life28','28天半衰期','#3B8595'),
        (HERE/'variants'/'online_primary','四候选每周选择','#D99951'),
        (HERE/'sensitivity'/'valid_residuals'/'variants'/'uniform56','仅排除回退残差','#56764A')]:
        d=pd.read_csv(folder/'daily_summary.csv')
        savings=(base_days.total_cost_yuan-d.total_cost_yuan).cumsum()/1e4
        axes[1].plot(pd.to_datetime(d.date),savings,label=name,color=color,lw=1.5)
    axes[1].axhline(0,color='#777777',lw=.8)
    axes[1].set(ylabel='累计节省（万元）',title='收益主要来自年初样本处理')
    axes[1].tick_params(axis='x',labelrotation=25)
    axes[1].legend(loc='lower right',fontsize=8)
    for ax in axes:ax.grid(axis='x',alpha=.15)
    dest=HERE/'figures';dest.mkdir(exist_ok=True)
    fig.savefig(dest/'window_comparison.png',dpi=320,bbox_inches='tight')
    fig.savefig(dest/'window_comparison.pdf',bbox_inches='tight')
    plt.close(fig)


if __name__=='__main__':main()
