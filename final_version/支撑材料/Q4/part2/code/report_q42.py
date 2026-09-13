"""Publish verified Q4-2 outputs, paper tables and inspected plot artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "results"
LABELS = dict(q2_repriced='原Q2按新电价结算', mean_price='历史预测：平均电价',
              joint_price='历史预测：联合场景', known_today_price='当日电价已知')
TARGET_DATES = ('2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21')
COLORS = dict(q2_repriced='#969696', mean_price='#C48436', joint_price='#277A8A',
              known_today_price='#7960A1')


def time_label(slot):
    return f'{slot//6:02d}:{slot%6*10:02d}'


def target_tables(detail, daily, primary):
    dest = HERE/'target_days'; dest.mkdir(exist_ok=True)
    purchases, storage, emergencies = [], [], []
    lines = ['# 第4问4-2指定日期结果', '',
             f'当前发布方案：{LABELS[primary]}。电量单位kWh，费用单位元；购电费按附件4实际电价结算。',
             '', '表内显示值四舍五入，汇总由未舍入明细计算。', '']
    for date in TARGET_DATES:
        frame = detail.loc[detail.date == date].reset_index(drop=True)
        day = daily.loc[daily.date == date].iloc[0]
        lines += [f'## {date}', '', '表1　计划购电量', '',
                  '| 时间段 | 购电量 | 时间段 | 购电量 | 时间段 | 购电量 |',
                  '|---|---:|---|---:|---|---:|']
        for slots in ((60, 72, 84), (96, 108, 120)):
            cells = []
            for slot in slots:
                span = time_label(slot)+'—'+time_label(slot+1)
                value = float(frame.g_kwh.iloc[slot])
                cells += [span, f'{value:,.4f}']
                purchases.append(dict(date=date, interval=span, planned_grid_kwh=value))
            lines.append('| '+' | '.join(cells)+' |')
        lines += ['', f'全天计划购电量：{day.g_kwh:,.4f} kWh；计划购电费：{day.planned_cost_yuan:,.2f}元；'
                  f'紧急购电费：{day.emergency_cost_yuan:,.2f}元；总购电费：{day.total_cost_yuan:,.2f}元。',
                  '', '表2　储能充放电量', '',
                  '| 时间段 | 充电量 | 放电量 | 时间段 | 充电量 | 放电量 |',
                  '|---|---:|---:|---|---:|---:|']
        for pair in ((0,1), (2,3), (4,5)):
            cells = []
            for block in pair:
                part = frame.iloc[block*24:(block+1)*24]
                span = time_label(block*24)+'—'+time_label((block+1)*24)
                charge, discharge = float(part.c_kwh.sum()), float(part.d_kwh.sum())
                cells += [span, f'{charge:,.4f}', f'{discharge:,.4f}']
                storage.append(dict(date=date, interval=span, charge_kwh=charge, discharge_kwh=discharge))
            lines.append('| '+' | '.join(cells)+' |')
        lines += ['', f'0:00储电量：{day.energy_start_kwh:,.4f} kWh；24:00储电量：{day.energy_end_kwh:,.4f} kWh。',
                  '', '表3　全部紧急购电区间', '', '| 时间段 | 紧急购电量 |', '|---|---:|']
        e = frame.emergency_kwh.to_numpy()
        cursor = 0
        while cursor < 144:
            if e[cursor] <= 1e-6:
                cursor += 1; continue
            start = cursor
            while cursor < 144 and e[cursor] > 1e-6:
                cursor += 1
            amount = float(e[start:cursor].sum())
            span = time_label(start)+'—'+time_label(cursor)
            emergencies.append(dict(date=date, interval=span, emergency_kwh=amount))
            lines.append(f'| {span} | {amount:,.4f} |')
        lines += ['', f'当日紧急购电量合计：{day.emergency_kwh:,.4f} kWh。', '']
    pd.DataFrame(purchases).to_csv(dest/'table1_grid.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(storage).to_csv(dest/'table2_storage.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(emergencies).to_csv(dest/'table3_emergency.csv', index=False, encoding='utf-8-sig')
    daily.loc[daily.date.isin(TARGET_DATES)].to_csv(dest/'daily_summary.csv', index=False, encoding='utf-8-sig')
    (HERE/'指定日期结果.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    verification = json.loads((HERE/'verification.json').read_text(encoding='utf-8'))
    information = json.loads((HERE/'information_verification.json').read_text(encoding='utf-8'))
    if not verification['pass_check'] or not information['pass_check']:
        raise RuntimeError('Physical, workbook and information checks must pass before publication')
    metadata = json.loads((HERE/'run_metadata.json').read_text(encoding='utf-8'))
    primary = metadata['primary_variant']
    folder = HERE/'variants'/primary
    comparison = pd.read_csv(HERE/'comparison.csv')
    costs = comparison.set_index('name')
    summary = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    for name in ('result4-2.xlsx', 'daily_summary.csv', 'schedule_detail.csv.gz'):
        shutil.copy2(folder/name, HERE/name)
    summary.update(primary_variant=primary,
        baseline_repriced_cost_yuan=float(costs.loc['q2_repriced'].total_cost_yuan),
        saving_vs_repriced_q2_yuan=float(costs.loc[primary].saving_vs_repriced_q2_yuan),
        saving_percent=float(costs.loc[primary].saving_percent),
        note='Primary follows the declared price-information model; mean-price contrast is slightly cheaper than joint-price in this retrospective year.')
    (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    detail = pd.read_csv(HERE/'schedule_detail.csv.gz')
    daily = pd.read_csv(HERE/'daily_summary.csv')
    baseline_detail = pd.read_csv(HERE/'variants'/'q2_repriced'/'schedule_detail.csv.gz')
    baseline_days = pd.read_csv(HERE/'variants'/'q2_repriced'/'daily_summary.csv')
    monthly_rows = []
    for name in comparison.name:
        frame = pd.read_csv(HERE/'variants'/name/'daily_summary.csv')
        changes = pd.DataFrame(dict(month=pd.to_datetime(frame.date).dt.month,
            cost_yuan=frame.total_cost_yuan,saving_yuan=baseline_days.total_cost_yuan-frame.total_cost_yuan))
        for month,row in changes.groupby('month').sum().iterrows():
            monthly_rows.append(dict(name=name,month=int(month),cost_yuan=row.cost_yuan,saving_yuan=row.saving_yuan))
    monthly = pd.DataFrame(monthly_rows)
    monthly.to_csv(HERE/'monthly_comparison.csv',index=False,encoding='utf-8-sig')
    target_tables(detail,daily,primary)
    data_summary = json.loads((HERE/'price_data_summary.json').read_text(encoding='utf-8'))
    joint_daily = pd.read_csv(HERE/'variants'/'joint_price'/'daily_summary.csv')
    clipped = int(joint_daily.clipped_scenario_price_count.sum())
    price_count = int(joint_daily.sample_count.sum()*144)
    joint, mean, baseline, known = [costs.loc[n] for n in ('joint_price','mean_price','q2_repriced','known_today_price')]
    lines = ['# 第4问4-2计算结果','',
        f'根目录发布方案：**{LABELS[primary]}**。完整策略见 [result4-2.xlsx](result4-2.xlsx)。',
        '', '**统计期为2025年2月1日至12月31日334天**，所有方案2月初储电量8550 kWh、年末6000 kWh。1月沿用Q2策略共同预热，不计入下表费用。',
        '', '## 1. 相同实际电价下的比较','',
        '| 方案 | 计划购电费（元） | 紧急购电费（元） | 总费用（元） | 较原Q2重新结算节省（元） |',
        '|---|---:|---:|---:|---:|']
    for name,row in costs.iterrows():
        lines.append(f'| {LABELS[name]} | {row.planned_cost_yuan:,.2f} | {row.emergency_cost_yuan:,.2f} | '
                     f'{row.total_cost_yuan:,.2f} | {row.saving_vs_repriced_q2_yuan:,.2f} |')
    lines += ['',f'联合场景模型比重新结算的Q2节省 **{joint.saving_vs_repriced_q2_yuan:,.2f}元（{joint.saving_percent:.4f}%）**。'
        f'计划费增加 {joint.planned_cost_yuan-baseline.planned_cost_yuan:,.2f} 元，紧急费减少 '
        f'{baseline.emergency_cost_yuan-joint.emergency_cost_yuan:,.2f} 元，合计费用下降。',
        '', f'紧急电量从 {baseline.emergency_kwh:,.2f} kWh降至 {joint.emergency_kwh:,.2f} kWh，'
        f'减少 {baseline.emergency_kwh-joint.emergency_kwh:,.2f} kWh；剩余弃置电量从 {baseline.dump_kwh:,.2f} kWh'
        f'增至 {joint.dump_kwh:,.2f} kWh。它体现更保守的高价缺电覆盖，不能只看紧急电量而忽略多买和弃置。',
        '', '原优化Q2在附件1固定电价下为14,389,135.08元。附件4改变了计费条件，不能直接把本问与该数字相减作为策略优劣。正确基准是保留Q2所有决策、按附件4重新结算后的15,184,704.23元。',
        '', '## 2. 哪些结论成立，哪些不能过度解释','',
        f'- 平均电价简化模型费用 **{mean.total_cost_yuan:,.2f}元**，比联合场景模型低 **{joint.total_cost_yuan-mean.total_cost_yuan:,.2f}元**。'
        '联合场景在本年度没有显示稳定优于均价近似的证据；若优先考虑实施简单，平均电价方案是完整可用的替代方案。',
        '- 默认主文件采用联合场景，是因为它对应所声明的电价与净负载同时不确定的模型，并非宣称它是这些回测方案中实际费用最低的一套。',
        f'- 当日电价已知对照费用 **{known.total_cost_yuan:,.2f}元**。它比联合场景低 '
        f'{joint.total_cost_yuan-known.total_cost_yuan:,.2f} 元，体现本次回测中更充分价格信息的价值；不是已证明的理论下界。',
        '- 已知电价对照仍使用预测负载和光伏，不读取未来真实净负载；48小时窗口中次日价格也只能预测。',
        '- 月度节省有正有负，结果不证明任意月份、其他年份均能改善，也不证明全局最优策略。',
        '', '## 3. 电价模型及数据检查','',
        '四个候选仅用1月8—31日的24个历史预测日比较RMSE，入选“最近4次同星期几均价”。2月起固定规则，没有用正式统计期费用选择预测参数。',
        f'附件4为365×144个完整正电价，范围 {data_summary["min"]:.4f}—{data_summary["max"]:.4f}元/kWh。'
        f'2—12月点预测RMSE为 {data_summary["report_rmse"]:.6f}元/kWh，MAE为 {data_summary["report_mae"]:.6f}元/kWh。',
        f'加性误差场景中的正数下限为0.001元/kWh，共有 {clipped} 个场景价格被截断，占 {price_count:,} 个场景价格的 '
        f'{100*clipped/price_count:.4f}%；原始实际价格没有截断。该下限是模型假设，未据回测费用调参。',
        '', '## 4. 指定日期结果','',
        '完整表1、表2、表3见 [指定日期结果.md](指定日期结果.md)，机器可读表格见 target_days/。',
        '', '| 日期 | 计划购电量（kWh） | 紧急购电量（kWh） | 计划费（元） | 紧急费（元） | 总费（元） |',
        '|---|---:|---:|---:|---:|---:|']
    for row in daily.loc[daily.date.isin(TARGET_DATES)].itertuples():
        lines.append(f'| {row.date} | {row.g_kwh:,.4f} | {row.emergency_kwh:,.4f} | {row.planned_cost_yuan:,.2f} | '
                     f'{row.emergency_cost_yuan:,.2f} | {row.total_cost_yuan:,.2f} |')
    lines += ['', 'Excel“全天购电费”填写计划购电费，与计划购电表一致；紧急费及总费另在逐日CSV、汇总JSON和上表中列明。',
        '', '## 5. 已完成核验','',
        '- 四套方案各48,096个正式时段全部通过独立附件核验：实际电价、净负载、能量守恒、0.9效率、功率、SOC、互斥、跨日连续、末日状态、紧急电量及费用。',
        '- 1月4,464个预热时段独立复算，从6000 kWh连续到8550 kWh；四套Excel均反读全部三个工作表及时间区间。',
        '- 人工篡改电价、储电量和紧急电量，核验器均能拒绝。',
        '- 固定电价退化例与原Q2目标值之差为0；两组价格—净负载配对解析例费用18,720元、30,240元，均与LP一致。',
        '- 对2月1日、6月1日、11月30日同时改动当天及未来价格、负载、光伏，历史预测主模型的当前预测、场景和控制量变化均为0。',
        '- 当日电价已知方案中，改变次日及以后实际价格，当前决策不变。源Q2代码、输出及原附件指纹未变。',
        '建模公式、信息口径、为什么仍可用LP以及分位数解释见 [建模说明.md](建模说明.md)。']
    (HERE/'结果说明.md').write_text('\n'.join(lines),encoding='utf-8')
    files = ('result4-2.xlsx','daily_summary.csv','schedule_detail.csv.gz')
    publication = dict(primary_variant=primary, physical_verification_passed=verification['pass_check'],
        information_verification_passed=information['pass_check'],
        published_files_identical=all((HERE/n).read_bytes()==(folder/n).read_bytes() for n in files),
        sha256={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in files})
    publication['pass_check'] = all(publication[k] for k in
        ('physical_verification_passed','information_verification_passed','published_files_identical'))
    (HERE/'publication_verification.json').write_text(json.dumps(publication,ensure_ascii=False,indent=2),encoding='utf-8')
    if not publication['pass_check']:
        raise RuntimeError('Published files do not match the verified variant')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
