"""Build the independent paper figure package from saved results, without solving models.

Run from any directory: python /path/to/paper/figure_package/build_figures.py
All outputs stay beside this script. Source result files are read-only.
"""
from pathlib import Path
import hashlib
import html
import json
import os
import platform
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'common/plotting'))
from setup_style import setup_style
from export_figure import export_figure

BLUE, ORANGE, GREEN = '#28718E', '#D89543', '#558568'
GRAY, INK, PURPLE = '#949DA5', '#273B49', '#80659B'
DATES = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
MODES = ['B_aligned', 'only_0', 'at_0_6', 'at_0_6_12', 'all']
STAGES = ['0点融合', '增加6点', '增加12点', '增加18点']
LABELS = ['历史预测', '0点融合', '0、6点', '0、6、12点', '四次更新']
WIDTH = 180 / 25.4
INPUTS, RECORDS, CHECKS = {}, [], []
CURRENT_SOURCES, CURRENT_TABLES = set(), []


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def source(relative):
    p = ROOT / relative
    INPUTS.setdefault(relative, digest(p))
    CURRENT_SOURCES.add(relative)
    return p


def csv(relative):
    return pd.read_csv(source(relative))


def begin():
    CURRENT_SOURCES.clear()
    CURRENT_TABLES.clear()


def table(name, frame):
    p = HERE / 'data' / (name + '.csv')
    frame.to_csv(p, index=False, encoding='utf-8-sig', float_format='%.12g')
    CURRENT_TABLES.append(p.relative_to(HERE).as_posix())


def check(name, condition):
    if not bool(condition):
        raise ValueError(name)
    CHECKS.append(name)


def close(a, b, atol=1e-5):
    return np.allclose(a, b, rtol=1e-9, atol=atol)


def pair(a, b, keys=('date', 'slot')):
    check('paired tables have unique keys', not a.duplicated(list(keys)).any() and not b.duplicated(list(keys)).any())
    aa, bb = a.set_index(list(keys)).sort_index(), b.set_index(list(keys)).sort_index()
    check('paired tables have identical keys', aa.index.equals(bb.index))
    return aa.reset_index(), bb.reset_index()


def panel(ax, title, ylabel=None):
    ax.set_title(title, loc='left', fontweight='bold', pad=7)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(axis='y', color='#E3E8EB', lw=.55)
    ax.set_axisbelow(True)


def hours(ax, label=True):
    ax.set_xlim(0, 24)
    ax.set_xticks([0, 6, 12, 18, 24])
    if label:
        ax.set_xlabel('时刻（h）')


def signed(ax, x, y, width=1/6):
    y = np.asarray(y)
    ax.bar(x, np.maximum(y, 0), width=width, color=BLUE, linewidth=0)
    ax.bar(x, np.minimum(y, 0), width=width, color=ORANGE, linewidth=0)
    ax.axhline(0, color=INK, lw=.65)


def legend(ax, **kw):
    ax.legend(frameon=False, **kw)


def waterfall(ax, start, changes, labels, totals=True, fmt='.2f'):
    """A zero-based cash/saving bridge. Inputs and displayed values use the same unit."""
    cumulative = start
    offset = 1 if totals else 0
    tops = []
    if totals:
        ax.bar(0, start, color=GRAY, width=.58)
        tops.append((0, start, format(start, fmt)))
    for j, value in enumerate(changes):
        x = j + offset
        nxt = cumulative + value
        ax.bar(x, abs(value), bottom=min(cumulative, nxt), width=.58,
               color=BLUE if value >= 0 else ORANGE)
        if x > 0:
            ax.plot([x-.71, x-.29], [cumulative]*2, color=GRAY, lw=.75)
        annotation = f'{value:+{fmt}}'
        if 0 < abs(value) < .005:
            annotation = f'{value:+.4f}'
        tops.append((x, max(cumulative, nxt), annotation))
        cumulative = nxt
    x = len(changes) + offset
    ax.bar(x, cumulative, color=INK, width=.58)
    tops.append((x, cumulative, format(cumulative, fmt)))
    ceiling = max(t[1] for t in tops)
    for x, y, text in tops:
        ax.annotate(text, (x, y), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=8)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylim(0, ceiling * 1.25)
    ax.axhline(0, lw=.65, color=INK)
    return cumulative


def finish(fig, ident, title, purpose, caption, body, method):
    fig.set_layout_engine('constrained', h_pad=.055, w_pad=.055, hspace=.10, wspace=.12)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    # Text outside the canvas is an export failure, not a cosmetic warning.
    outside = []
    inactive_ticks = set()
    for ax in fig.axes:
        for axis, limits in [(ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())]:
            lo, hi = sorted(limits)
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not lo-1e-9 <= tick.get_loc() <= hi+1e-9:
                    inactive_ticks.update([id(tick.label1), id(tick.label2)])
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text() and id(text) not in inactive_ticks:
            box = text.get_window_extent(renderer)
            if box.x0 < -2 or box.y0 < -2 or box.x1 > fig.bbox.width+2 or box.y1 > fig.bbox.height+2:
                outside.append(text.get_text())
    check(ident + ': text inside canvas ' + repr(outside), not outside)
    export_figure(fig, str(HERE/'figures'/ident), formats=['pdf', 'png'], dpi=320, tight=False)
    RECORDS.append(dict(id=ident, title=title, purpose=purpose, caption=caption,
                        body=body, method=method, inputs=sorted(CURRENT_SOURCES),
                        tables=list(CURRENT_TABLES), width_mm=180,
                        height_mm=round(fig.get_size_inches()[1]*25.4, 2)))
    plt.close(fig)


def q1():
    begin()
    with np.load(source('question1/results/solution.npz'), allow_pickle=False) as f:
        d = {k: f[k].copy() for k in f.files if k != 'labels'}
    base = np.maximum(d['load']-d['pv'], 0)
    check('Q1 cost equals original NPZ objective', close(d['price'] @ d['g'], d['obj_lp']))
    check('Q1 baseline independently calculated', close(d['price'] @ base, d['base_cost']))
    e0 = d['E'][0]-.9*d['c'][0]+d['d'][0]/.9
    check('Q1 initial and terminal energy', close(e0, 6000) and close(d['E'][-1], e0))
    x = (np.arange(144)+.5)/6
    frame = pd.DataFrame(dict(slot=np.arange(144), hour_center=x, price=d['price'],
        load_kw=d['load']*6, pv_kw=d['pv']*6, grid_kw=d['g']*6,
        charge_kw=d['c']*6, discharge_kw=d['d']*6, energy_after_kwh=d['E']))
    table('01_q1_dispatch', frame)
    fig, ax = plt.subplots(4, 1, figsize=(WIDTH, 6.9), sharex=True)
    ax[0].stairs(d['price'], np.arange(145)/6, baseline=None, color=PURPLE)
    panel(ax[0], '(a) 分时电价', '电价（元/kWh）')
    ax[0].set_ylim(0, 1.65)
    ax[1].plot(x, d['load']*6, color=INK, ls='--', label='负载')
    ax[1].plot(x, d['pv']*6, color=ORANGE, label='光伏')
    ax[1].stairs(d['g']*6, np.arange(145)/6, baseline=None, color=BLUE, label='购电')
    panel(ax[1], '(b) 供需与外网购电', '功率（kW）')
    ax[1].set_ylim(0, 12500)
    legend(ax[1], loc='upper center', ncol=3)
    signed(ax[2], x, (d['c']-d['d'])*6)
    panel(ax[2], '(c) 充电为正，放电为负', '储能功率（kW）')
    ax[2].set_ylim(-5200, 6200)
    ax[3].plot(np.arange(145)/6, np.r_[e0, d['E']], color=GREEN)
    ax[3].axhline(1200, color=GRAY, ls='--', lw=.8)
    ax[3].axhline(10800, color=GRAY, ls='--', lw=.8)
    ax[3].scatter([0, 24], [e0, d['E'][-1]], s=18, color=GREEN, zorder=5)
    panel(ax[3], '(d) 储能状态与容量边界', '储电量（kWh）')
    ax[3].set_ylim(0, 12300)
    ax[3].annotate('首末均为6000 kWh', (24, 6000), xytext=(-7, 14),
                   textcoords='offset points', ha='right', color=GREEN, fontsize=8)
    for a in ax:
        hours(a, label=False)
        for l, r in [(6, 9), (18, 21)]:
            a.axvspan(l, r, color=PURPLE, alpha=.055, zorder=-1)
    hours(ax[-1])
    finish(fig, '01_q1_dispatch', '问题一：分时电价、供需与储能调度',
        '解释储能如何协调分时电价、光伏供给和负载，并满足首末电量约束。',
        '典型日确定性调度结果。四个面板共享时间轴，依次展示电价、供需与购电功率、储能充放电功率及储电量；水平虚线为1200和10800 kWh的储电量边界，浅色背景仅辅助定位早晚时段。',
        f'在已知电价、负载和光伏的典型日中，优化购电费为{float(d["obj_lp"]):,.2f}元。储能在部分低价时段及光伏富余时段充电，在高价时段放电；购电与充放电的联合安排改变了电量的时段分布。储电量始终位于规定区间内，且日初、日末均为6000 kWh，因此该收益并非通过消耗日初库存获得。',
        '读取完整精度solution.npz；每10分钟电量乘6换算为功率；状态曲线含0时初值和144个段末值。浅色时段不参与任何统计分组。')

    begin()
    source('question1/results/solution.npz')
    delta = d['g']-base
    extra = np.maximum(delta, 0) @ d['price']
    avoided = np.maximum(-delta, 0) @ d['price']
    saving = float(d['base_cost']-d['obj_lp'])
    check('Q1 cash bridge closes', close(avoided-extra, saving))
    table('02_q1_grid_shift', pd.DataFrame(dict(slot=np.arange(144), hour_center=x,
          baseline_kwh=base, optimized_kwh=d['g'], delta_kwh=delta,
          price=d['price'], cost_delta_yuan=delta*d['price'])))
    table('02_q1_cost_bridge', pd.DataFrame(dict(item=['baseline', 'avoided', 'extra', 'optimized'],
          value_yuan=[float(d['base_cost']), -avoided, extra, float(d['obj_lp'])])))
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.15), gridspec_kw={'width_ratios':[1.05, 1]})
    signed(ax[0], x, delta*6)
    panel(ax[0], '(a) 相对无储能基线的购电转移', '购电功率差（kW）')
    hours(ax[0])
    ax[0].text(.03, .96, '正：增购   负：少购', transform=ax[0].transAxes, va='top', fontsize=8)
    ax[0].set_ylim(-5300, 6900)
    waterfall(ax[1], float(d['base_cost'])/1e4, [-avoided/1e4, extra/1e4],
              ['无储能', '少购\n减费', '增购\n加费', '优化后'])
    panel(ax[1], '(b) 逐时段购电费差额闭合', '购电费（万元）')
    finish(fig, '02_q1_savings', '问题一：购电转移与费用节省的账面分解',
        '区分增购与少购，说明为什么部分时段多买电，全天费用仍然下降。',
        '储能调度相对无储能基线的购电差异与费用桥接。左图为优化购电功率减去无储能购电功率；右图按同一时段电价分别累计少购所减少的费用和增购所增加的费用。',
        f'无储能时的购电费为{float(d["base_cost"]):,.2f}元。储能使部分时段少购电，对应费用减少{avoided:,.2f}元；同时在另一些时段增购电，对应费用增加{extra:,.2f}元。两者抵消后净节省{saving:,.2f}元，降幅为{saving/float(d["base_cost"])*100:.2f}%。这一分解是逐时段购电费差额的恒等核算，不将同一节省进一步归因为独立的“光伏消纳效应”或“套利效应”。',
        '基线=max(负载−光伏,0)；少购减费=sum[p*max(基线−优化,0)]，增购加费=sum[p*max(优化−基线,0)]。弃光、能量损失及储能约束仍由原模型决定。')


def q2():
    begin()
    allc = csv('question2/results/all_comparisons.csv')
    raw = allc[allc.first_residual_index == 0].set_index('name')
    clean = allc[allc.first_residual_index == 7].set_index('name')
    old, new = pair(csv('question2/results/variants/uniform56/daily_summary.csv'),
                    csv('question2/results/daily_summary.csv'), keys=('date',))
    check('Q2 334 paired days', len(new) == 334)
    s = old.total_cost_yuan-new.total_cost_yuan
    total = s.sum()
    check('Q2 daily savings match comparison', close(total, raw.loc['uniform56', 'total_cost_yuan']-clean.loc['uniform56', 'total_cost_yuan']))
    check('Q2 no change after March 4', close(s[new.date >= '2025-03-05'], 0))
    plan = raw.loc['uniform56', 'planned_cost_yuan']-clean.loc['uniform56', 'planned_cost_yuan']
    emergency = raw.loc['uniform56', 'emergency_cost_yuan']-clean.loc['uniform56', 'emergency_cost_yuan']
    check('Q2 savings components close', close(plan+emergency, total))
    table('03_q2_all_11_comparisons', allc)
    table('03_q2_daily_savings', pd.DataFrame(dict(date=new.date, original_cost=old.total_cost_yuan,
          published_cost=new.total_cost_yuan, saving_yuan=s, cumulative_saving_yuan=s.cumsum())))
    fig = plt.figure(figsize=(WIDTH, 5.55))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1])
    a, b, c = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    names = ['uniform56', 'half_life28', 'online_primary']
    baseline = raw.loc['uniform56', 'total_cost_yuan']
    for i, name in enumerate(names):
        v = [(baseline-raw.loc[name, 'total_cost_yuan'])/1e4,
             (baseline-clean.loc[name, 'total_cost_yuan'])/1e4]
        a.plot(v, [i, i], color='#CFD6DB', lw=2, zorder=1)
        a.scatter(v[0], i, color=GRAY, marker='o', s=34, zorder=3)
        a.scatter(v[1], i, color=BLUE, marker='D', s=34, zorder=3)
    a.axvline(0, color=GRAY, ls=':', lw=.8)
    a.set_yticks(range(3), ['56天等权', '半衰期28天', '每周选择'])
    a.set_ylim(2.6, -.7)
    a.set_xlim(-.7, 1.6)
    panel(a, '(a) 同一规则的残差口径配对')
    a.set_xlabel('相对原56天等权方案节省（万元）')
    a.legend(handles=[Line2D([], [], color=GRAY, marker='o', ls='', label='原残差'),
        Line2D([], [], color=BLUE, marker='D', ls='', label='有效残差')], loc='lower right', frameon=False, fontsize=7.5)
    vals = np.array([plan, emergency, total])/1e4
    bars = b.barh(range(3), vals, color=[BLUE, ORANGE, INK], height=.52)
    for i, v in enumerate(vals):
        if v < 0:
            b.text(v/2, i, f'{v:+.2f}', color='white', ha='center', va='center', fontsize=8)
        else:
            b.annotate(f'{v:+.2f}', (v, i), xytext=(4, 0), textcoords='offset points', va='center', fontsize=8)
    b.set_yticks(range(3), ['计划费', '紧急费', '合计'])
    b.invert_yaxis()
    b.set_xlim(-4.6, 6.2)
    b.axvline(0, color=GRAY, lw=.8)
    panel(b, '(b) 最终方案节省的来源')
    b.set_xlabel('原方案费用 − 最终费用（万元）')
    days = pd.to_datetime(new.date)
    c.plot(days, s.cumsum()/1e4, color=BLUE, lw=1.6)
    c.axvline(pd.Timestamp('2025-03-05'), color=GRAY, ls='--', lw=.8)
    c.axhline(0, color=GRAY, lw=.7)
    c.set_xlim(days.min(), days.max())
    c.set_ylim(-.08, 2.0)
    c.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[2, 4, 6, 8, 10, 12]))
    c.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    c.text(.36, .83, f'累计节省 {total/1e4:.4f} 万元\n3月5日起，逐日费用完全一致',
           transform=c.transAxes, fontsize=9, color=BLUE)
    c.set_xlabel('2025年')
    panel(c, '(c) 改善集中在启动阶段', '累计节省（万元）')
    finish(fig, '03_q2_residuals', '问题二：残差样本口径、成本权衡与启动期收益',
        '说明最终选择有效残差与56天等权的依据，以及收益发生的时间和代价。',
        '残差口径的配对比较及最终方案相对原方案的费用变化。(a)连线连接同一窗口规则在两种残差口径下的年度费用点，不是置信区间；(b)分解计划费与紧急费的节省；(c)展示全年累计节省。',
        f'在具有两种残差口径的三种窗口规则中，排除1月1—7日回退预测残差后，56天等权方案的回测费用最低，为{clean.loc["uniform56","total_cost_yuan"]:,.2f}元。最终方案计划费减少{plan:,.2f}元，紧急费增加{-emergency:,.2f}元，净节省{total:,.2f}元。累计收益于启动阶段形成，3月5日至12月31日逐日费用与原方案一致。因此，该改进应解释为残差样本口径调整在启动期的作用，不能据此声称全年持续适应能力提高，也不能据同年回测证明56天窗口对其他年份最优。',
        '费用期为2月1日至12月31日334天；原/新方案初末储电量均为8550/6000 kWh。(a)仅选有完整配对的三种规则；11项实验全部保留在数据表中，未生成虚构置信区间。(c)按日期配对累计，不截去后续无差异时段。')


def q3_value():
    begin()
    comp = csv('question3/results/comparison.csv').set_index('mode').loc[MODES]
    costs = comp.total_cost_yuan.to_numpy()
    incremental = -np.diff(costs)
    check('Q3 increments telescope', close(incremental.sum(), costs[0]-costs[-1]))
    table('04_q3_update_values', comp.reset_index().assign(
        incremental_saving_yuan=np.r_[0, incremental], cumulative_saving_yuan=costs[0]-costs))
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.25))
    waterfall(ax[0], 0, incremental/1e4,
              ['0点\n融合', '加6点', '加12点', '加18点', '合计'], totals=False)
    panel(ax[0], '(a) 逐级增加预报与调整机会', '费用节省（万元）')
    ax[0].text(.04, .9, f'18点增量：{incremental[-1]:+.2f}元', transform=ax[0].transAxes,
               fontsize=8, color=INK)
    bars = ax[1].bar(range(5), comp.emergency_kwh/1e4,
                    color=[GRAY, BLUE, BLUE, BLUE, INK], width=.58)
    ax[1].bar_label(bars, fmt='%.2f', padding=4, fontsize=8)
    ax[1].set_xticks(range(5), ['历史\n预测', '0点', '0、6', '0、6\n12', '四次\n更新'])
    ax[1].set_ylim(0, 30)
    panel(ax[1], '(b) 紧急购电量的同步变化', '紧急电量（万kWh）')
    finish(fig, '04_q3_information_value', '问题三：预报融合与日内调整的逐级收益',
        '区分0点预报融合的价值与6、12、18点调整的增量，不把信息更新次数等同于严格改善。',
        '固定电价情形下的逐级费用节省与紧急购电量。费用节省以本问同口径历史预测对照为起点，依次引入0点融合预报和6、12、18点调整；右图按相同顺序比较紧急购电量。',
        f'四次更新主方案的总费用为{costs[-1]:,.2f}元，相对本问同口径历史预测对照节省{costs[0]-costs[-1]:,.2f}元。仅引入0点融合预报节省{incremental[0]:,.2f}元，随后增加6点和12点更新分别节省{incremental[1]:,.2f}元和{incremental[2]:,.2f}元；增加18点后费用变化为+{-incremental[3]:.2f}元，本年度未显示明确的额外经济收益。四次更新仍作为预设主方案保留。有限经验场景、重新聚类及滚动执行使真实回测费用不必随更新机会增加而严格下降。',
        '每次增量为相邻两项已保存总费用之差；不是不同问主方案的直接相减。此对照初末储电量均为6000 kWh，与第二问发布结果的初值不同，不能直接替换第二问费用。负的节省表示费用上升。')


def q3_fusion():
    begin()
    diag = csv('question3/results/forecast_diagnostics.csv')
    avg = diag.groupby('issue_hour')[['history_mae_kw', 'external_mae_kw', 'fusion_mae_kw']].mean()
    check('Q3 forecast diagnostics complete', len(diag)==334*4 and diag.groupby('issue_hour').size().eq(334).all())
    check('Q3 fusion weights bounded', diag.alpha_next_6h.between(0, 1).all())
    table('05_q3_forecast_mae', avg.reset_index())
    table('05_q3_forecast_diagnostics', diag)
    fig = plt.figure(figsize=(WIDTH, 4.9))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.05])
    a, b, c = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    names = ['历史预测', '发布预报', '在线融合']
    for ax, stages in [(a, [6, 12]), (b, [0, 18])]:
        for i, (col, lab, color) in enumerate(zip(avg.columns, names, [GRAY, PURPLE, BLUE])):
            vals = avg.loc[stages, col].to_numpy()
            bars = ax.bar(np.arange(2)+(i-1)*.24, vals, .23, label=lab, color=color)
            ax.bar_label(bars, fmt='%.1f', padding=2, fontsize=7)
        ax.set_xticks(range(2), [f'{h}—{h+6}时' for h in stages])
    panel(a, '(a) 日间预测误差', 'MAE（kW）')
    panel(b, '(b) 夜间预测误差', 'MAE（kW）')
    a.set_ylim(0, 410)
    b.set_ylim(0, 14)
    legend(a, loc='upper right', fontsize=7)
    colors = [GRAY, BLUE, ORANGE, PURPLE]
    for h, color, ls in zip([0, 6, 12, 18], colors, ['--', '-', '-', ':']):
        g = diag[diag.issue_hour==h].sort_values('date')
        c.plot(pd.to_datetime(g.date), g.alpha_next_6h, color=color, ls=ls, label=f'{h}点发布', lw=.95)
    c.set_ylim(-.05, 1.22)
    c.set_yticks([0, .5, 1])
    c.set_xlim(pd.Timestamp('2025-02-01'), pd.Timestamp('2025-12-31'))
    c.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[2, 4, 6, 8, 10, 12]))
    c.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    c.set_xlabel('2025年')
    panel(c, '(c) 面向下一执行段的发布预报权重', '融合权重')
    legend(c, loc='upper center', ncol=4, fontsize=8)
    finish(fig, '05_q3_forecast_fusion', '问题三：预报融合误差与权重变化',
        '展示融合预测的精度及动态权重；分开日间与夜间尺度，避免日间大值掩盖夜间误差。',
        '发布后六小时光伏预测误差及融合权重。(a)(b)分别比较日间和夜间的历史预测、发布预报及在线融合MAE，两面板纵轴尺度不同；(c)展示各发布时间对应的发布预报权重。',
        f'6—12时段的MAE由历史预测的{avg.loc[6,"history_mae_kw"]:.2f} kW降至融合预测的{avg.loc[6,"fusion_mae_kw"]:.2f} kW，12—18时段由{avg.loc[12,"history_mae_kw"]:.2f} kW降至{avg.loc[12,"fusion_mae_kw"]:.2f} kW。夜间绝对误差较小，单独绘制以保留其变化尺度。融合权重随历史已成熟样本更新，并包含原算法的偏差修正，因此融合输出不只是当期两条预报的固定加权平均。MAE改善本身不等同于等比例的费用下降，经济效果需结合更新频率对照判断。',
        '每个发布时间334天、每天36个十分钟误差；先每日求MAE再等权平均，与这些等长度区间的总体MAE一致。权重为原诊断中的alpha_next_6h；未重估参数。4-3共用此预测诊断，不重复作图。')


def q3_dispatch():
    begin()
    allg = csv('question3/results/schedule_detail.csv')
    detail = allg[allg.date.isin(DATES)].sort_values(['date', 'slot'])
    check('Q3 four full requested days', len(detail)==576)
    out = detail.copy()
    out['delta_grid_kw'] = (out.adjusted_kwh-out.original_kwh)*6
    table('06_q3_adjustments', out)
    maxdiff = max(abs(out.delta_grid_kw).max()*1.18, 1)
    fig, ax = plt.subplots(4, 2, figsize=(WIDTH, 6.35), sharex=True, sharey='col')
    for row, date in enumerate(DATES):
        g = out[out.date==date]
        x = (g.slot.to_numpy()+.5)/6
        signed(ax[row, 0], x, g.delta_grid_kw)
        ax[row, 0].set_ylim(-maxdiff, maxdiff)
        ax[row, 0].set_ylabel(date[5:]+'\n功率差（kW）')
        ax[row, 1].plot(np.arange(145)/6, np.r_[g.energy_before_kwh.iloc[0], g.energy_after_kwh], color=GREEN)
        for e in (1200, 10800):
            ax[row, 1].axhline(e, color=GRAY, ls='--', lw=.65)
        emergency = g.emergency_kwh.to_numpy() > 1e-6
        ax[row, 1].plot(x[emergency], np.full(emergency.sum(), 650), '|', color=ORANGE, ms=5, mew=1.2)
        ax[row, 1].set_ylim(0, 12600)
        ax[row, 1].set_ylabel('储电量（kWh）')
        for a in ax[row]:
            hours(a, False)
            a.grid(axis='y', color='#E3E8EB', lw=.55)
            for h in (6, 12, 18):
                a.axvline(h, color=GRAY, ls=':', lw=.65)
    panel(ax[0, 0], '(a) 最终执行购电 − 0点原计划')
    panel(ax[0, 1], '(b) 储能状态与紧急购电时段')
    ax[0, 0].text(.03, .92, '蓝：增购  橙：减购', transform=ax[0, 0].transAxes, fontsize=7, va='top')
    ax[0, 1].text(.04, .94, '底部橙线：发生紧急购电', transform=ax[0, 1].transAxes, fontsize=7, va='top')
    for a in ax[-1]: hours(a)
    finish(fig, '06_q3_rolling_adjustment', '问题三：日内购电修正及储能衔接',
        '突出日内修正而非两条几乎重合的绝对购电曲线，同时展示紧急补购出现在哪些时段。',
        '四个指定日的日内计划修正与储能状态。左列为最终执行购电相对0点原计划的功率差，正值为增购、负值为减购；右列为储电量，底部橙色短线标记紧急购电大于数值容差的时段。竖虚线表示6、12、18点发布时刻。',
        '日内更新后的购电修正相对原计划较小，直接叠加两条绝对购电曲线容易掩盖变化。以原计划为零基准后，可以清楚识别各执行区间内的增购和减购。储电量按跨日滚动过程衔接，指定日的首末电量不要求逐日相等。紧急购电标记说明计划与储能联合执行后仍可能存在实际供需缺口；该标记只表示发生时间，不表示缺口大小，也不能据其与储能状态的相邻关系断言单一原因。',
        '按date/slot排序，保留每个指定日全部144段；(adjusted−original)*6为功率差。该差值是每段最终执行量与0点计划的比较，不是6/12/18点完整计划版本之间的差。短线阈值为1e-6 kWh。')


def q42_value():
    begin()
    comp = csv('question4/part2/results/comparison.csv').set_index('name')
    monthly = csv('question4/part2/results/monthly_comparison.csv')
    names = ['mean_price', 'joint_price', 'known_today_price']
    base = comp.loc['q2_repriced']
    savings = pd.DataFrame(dict(name=names,
        planned_saving_yuan=[base.planned_cost_yuan-comp.loc[n,'planned_cost_yuan'] for n in names],
        emergency_saving_yuan=[base.emergency_cost_yuan-comp.loc[n,'emergency_cost_yuan'] for n in names],
        total_saving_yuan=[base.total_cost_yuan-comp.loc[n,'total_cost_yuan'] for n in names]))
    check('Q42 decomposition closes', close(savings.planned_saving_yuan+savings.emergency_saving_yuan, savings.total_saving_yuan))
    table('07_q42_savings', savings)
    table('07_q42_monthly', monthly)
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.45), gridspec_kw={'width_ratios':[1.03,1]})
    for j, col in enumerate(['planned_saving_yuan', 'emergency_saving_yuan']):
        ax[0].barh(np.arange(3)+(j-.5)*.23, savings[col]/1e4, height=.21,
                   color=[BLUE, ORANGE][j], label=['计划费节省', '紧急费节省'][j])
    ax[0].scatter(savings.total_saving_yuan/1e4, range(3), color=INK, marker='D', s=28, zorder=5, label='合计')
    for i, v in enumerate(savings.total_saving_yuan/1e4):
        ax[0].annotate(f'{v:.2f}', (v, i), xytext=(6, -21), textcoords='offset points', fontsize=8)
    ax[0].set_yticks(range(3), ['均价预测', '联合场景', '当日电价\n已知'])
    ax[0].set_ylim(2.5, -.95)
    ax[0].set_xlim(-7, 19)
    ax[0].axvline(0, color=GRAY, lw=.75)
    panel(ax[0], '(a) 同一实际电价下的节省')
    ax[0].set_xlabel('原Q2重新结算 − 对照方案（万元）')
    legend(ax[0], loc='upper left', fontsize=7, ncol=2)
    for n, color, marker in [('mean_price', PURPLE, 's'), ('joint_price', BLUE, 'o')]:
        g = monthly[monthly.name==n].sort_values('month')
        check('Q42 monthly agrees with annual '+n, close(g.saving_yuan.sum(), savings.set_index('name').loc[n,'total_saving_yuan']))
        ax[1].plot(g.month, g.saving_yuan/1e4, color=color, marker=marker, ms=3.5,
                   label='均价预测' if n=='mean_price' else '联合场景')
    ax[1].axhline(0, color=GRAY, lw=.8)
    ax[1].set_xticks([2, 4, 6, 8, 10, 12])
    ax[1].set_xlabel('月份')
    ax[1].set_ylim(-.7, 1.85)
    panel(ax[1], '(b) 收益并非每月均为正', '月度节省（万元）')
    legend(ax[1], loc='upper left', fontsize=8)
    joint = comp.loc['joint_price']
    finish(fig, '07_q42_price_information', '4-2：价格信息的费用权衡与月度表现',
        '在同一实际电价下比较策略；展示主方案为何多支付计划费，以及更充分价格信息的回测价值。',
        '相对原第二问策略按附件4电价重新结算的费用节省。左图将节省分为计划费与紧急费，菱形表示合计，负值表示该项费用增加；右图展示均价预测与联合场景的月度净节省。当日电价已知为信息对照。',
        f'联合场景主方案的总费用为{joint.total_cost_yuan:,.2f}元。相对原Q2重新结算，其计划费增加{joint.planned_cost_yuan-base.planned_cost_yuan:,.2f}元，而紧急费减少{base.emergency_cost_yuan-joint.emergency_cost_yuan:,.2f}元，净节省{base.total_cost_yuan-joint.total_cost_yuan:,.2f}元。均价预测方案在本年度比联合场景低{joint.total_cost_yuan-comp.loc["mean_price","total_cost_yuan"]:,.2f}元，因此不能宣称联合场景取得了回测最低费用。已知当日电价对照比联合场景低{joint.total_cost_yuan-comp.loc["known_today_price","total_cost_yuan"]:,.2f}元，体现更充分价格信息的回测价值，但不构成理论最优下界。月度节省存在正负变化，年度改善不保证各月均改善。',
        '四方案均使用相同附件4实际价格、334天及8550/6000 kWh初末电量；费用差按已保存comparison.csv核算。已知当日价格对照仍预测负载/光伏及次日价格。')


def q42_dispatch():
    begin()
    old, new = pair(csv('question4/part2/results/variants/q2_repriced/schedule_detail.csv.gz'),
                    csv('question4/part2/results/schedule_detail.csv.gz'))
    check('Q42 identical realized prices', close(old.price_yuan_per_kwh, new.price_yuan_per_kwh))
    new['delta_grid_kw'] = (new.g_kwh-old.g_kwh)*6
    g4 = new[new.date.isin(DATES)].copy()
    table('08_q42_price_and_shift', g4)
    limit = abs(g4.delta_grid_kw).max()*1.15
    fig, ax = plt.subplots(4, 2, figsize=(WIDTH, 6.35), sharex=True, sharey='col')
    for row, date in enumerate(DATES):
        g = g4[g4.date==date]
        x = (g.slot.to_numpy()+.5)/6
        a, b = ax[row]
        a.plot(x, g.price_yuan_per_kwh, color=INK, label='实际电价')
        a.plot(x, g.objective_price_yuan_per_kwh, color=PURPLE, ls='--', label='场景均价')
        a.fill_between(x, g.price_yuan_per_kwh, g.objective_price_yuan_per_kwh, color=PURPLE, alpha=.13)
        a.set_ylabel(date[5:]+'\n元/kWh')
        a.set_ylim(0, 1.85)
        signed(b, x, g.delta_grid_kw)
        b.set_ylabel('功率差（kW）')
        b.set_ylim(-limit, limit)
        for v in (a, b):
            hours(v, False)
            v.grid(axis='y', color='#E3E8EB', lw=.55)
    panel(ax[0, 0], '(a) 实际电价与优化采用的均价')
    panel(ax[0, 1], '(b) 联合场景购电 − 原Q2购电')
    legend(ax[0, 0], loc='upper left', ncol=2, fontsize=7)
    for a in ax[-1]: hours(a)
    finish(fig, '08_q42_schedule_shift', '4-2：价格偏差与日前购电的时段重排',
        '连接价格输入与购电差异，覆盖四个题目指定日，不只选择一个表现较好的日期。',
        '四个指定日的实际电价、优化采用的场景均价及购电计划差异。左列阴影仅表示两条价格曲线的差距；右列为联合场景计划购电功率减去原Q2计划购电功率，蓝色为增购、橙色为少购。',
        '将原第二问策略作为参照，可以观察到价格信息模型引入后购电时段发生重排。场景均价与实际电价并不处处一致，价格曲线形状接近也不保证决策完全相同。联合场景的决策还依赖价格与净负载误差的配对、储能约束及前期形成的状态，因此左、右两列用于对照现象，不将每个购电差值单独归因于同一时段的价格预测误差。此处展示的是日前计划，不应描述为当天观察实际价格后的日内修正。',
        '原Q2重新结算策略保留原购电决策，仅改结算价格。按date/slot一对一配对；四日均为144段；功率差=(joint.g−repriced.g)*6。阴影不是预测区间；场景均价不是完整联合场景的替代模型。')


def q43_value():
    begin()
    a = csv('question3/results/comparison.csv').set_index('mode').loc[MODES]
    b = csv('question4/part3/results/comparison.csv').set_index('mode').loc[MODES]
    check('Q3 Q43 equal period and endpoint energy',
          close(a[['days', 'initial_energy_kwh', 'final_energy_kwh']], b[['days', 'initial_energy_kwh', 'final_energy_kwh']]))
    cols = ['planned_cost_yuan', 'adjustment_net_yuan', 'emergency_cost_yuan']
    delta = b.loc['all', cols].astype(float)-a.loc['all', cols].astype(float)
    gap = b.loc['all','total_cost_yuan']-a.loc['all','total_cost_yuan']
    check('Q43 cost difference closes', close(delta.sum(), gap))
    inc3 = -np.diff(a.total_cost_yuan.to_numpy())
    inc4 = -np.diff(b.total_cost_yuan.to_numpy())
    table('09_q43_cost_gap', pd.DataFrame(dict(item=cols, q3_yuan=a.loc['all',cols].astype(float).to_numpy(),
          q43_yuan=b.loc['all',cols].astype(float).to_numpy(), difference_yuan=delta.to_numpy())))
    table('09_q43_increment_comparison', pd.DataFrame(dict(stage=STAGES, q3_saving_yuan=inc3, q43_saving_yuan=inc4)))
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.4))
    waterfall(ax[0], 0, delta.to_numpy()/1e4, ['原计划费', '净调整费', '紧急费', '合计'], totals=False)
    panel(ax[0], '(a) 两种运行情形的费用差额', '4-3 − 第三问（万元）')
    for i, (vals, color, name) in enumerate([(inc3, GRAY, '第三问'), (inc4, BLUE, '4-3')]):
        bars = ax[1].bar(np.arange(4)+(i-.5)*.34, vals/1e4, .31, color=color, label=name)
        ax[1].bar_label(bars, labels=[f'{v/1e4:.4f}' if 0<abs(v)<50 else f'{v/1e4:.2f}' for v in vals], padding=3, fontsize=7)
    ax[1].set_xticks(range(4), ['0点\n融合', '加6点', '加12点', '加18点'])
    ax[1].set_ylim(-2.5, 30)
    ax[1].axhline(0, color=GRAY, lw=.8)
    panel(ax[1], '(b) 各自内部的逐级增量对照', '相邻方案节省（万元）')
    legend(ax[1], loc='upper right', fontsize=8)
    finish(fig, '09_q43_incremental_comparison', '4-3：相对第三问的费用差额与更新收益',
        '把跨情形的账面差额和各情形内部的更新收益分开，避免将不同价格下的费用差当作策略优劣。',
        '4-3与第三问主方案的费用差额及更新收益比较。左图按原计划费、净调整费和紧急费分解4-3减第三问的总费用差；右图分别在两问内部计算相邻更新方案之间的费用节省。',
        f'4-3主方案费用为{b.loc["all","total_cost_yuan"]:,.2f}元，比第三问高{gap:,.2f}元。其中紧急费差额为{delta["emergency_cost_yuan"]:,.2f}元，占总差额的{delta["emergency_cost_yuan"]/gap*100:.2f}%。该结果是不同电价输入及对应滚动策略共同形成的账面差异，不能全部解释为电价波动或预测误差的因果成本。在各自内部的逐级对照中，增加6点更新的节省由第三问的{inc3[1]/1e4:.2f}万元变为4-3的{inc4[1]/1e4:.2f}万元，增加12点由{inc3[2]/1e4:.2f}万元变为{inc4[2]/1e4:.2f}万元；4-3增加18点节省{inc4[3]:,.2f}元，而第三问费用增加{-inc3[3]:.2f}元。这表明新增调整机会的回测价值随运行情形而变化。',
        '两问334天、初末电量6000 kWh相同；价格过程与滚动状态不同。净调整费已包含增购、退款及违约费，不重复叠加。跨问差额只作账面描述；内部增量依据各自comparison.csv，未新增反事实优化实验。')


def q43_shift():
    begin()
    a, b = pair(csv('question3/results/schedule_detail.csv'), csv('question4/part3/results/schedule_detail.csv'))
    check('Q3 Q43 realized load/PV identical', close(a[['load_kwh','pv_kwh']], b[['load_kwh','pv_kwh']]))
    fields = [('price_yuan_per_kwh', 1, '电价差（元/kWh）'),
              ('adjusted_kwh', 6, '执行购电功率差（kW）'),
              ('energy_after_kwh', 1, '段末储电量差（kWh）')]
    frame = b[['date', 'slot']].copy()
    for field, scale, label in fields:
        frame[field+'_difference'] = (b[field]-a[field])*scale
    frame = frame[frame.date.isin(DATES)].copy()
    table('10_q43_paired_differences', frame)
    state = pd.DataFrame([dict(date=date,
        q3_energy_start_kwh=float(a[a.date==date].energy_before_kwh.iloc[0]),
        q43_energy_start_kwh=float(b[b.date==date].energy_before_kwh.iloc[0])) for date in DATES])
    table('10_q43_initial_states', state)
    cmap = LinearSegmentedColormap.from_list('difference', [ORANGE, '#FAFAF8', BLUE])
    fig, ax = plt.subplots(3, 1, figsize=(WIDTH, 5.6), sharex=True)
    for i, (field, scale, label) in enumerate(fields):
        values = frame.pivot(index='date', columns='slot', values=field+'_difference').loc[DATES].to_numpy()
        check('Q43 heatmap preserves 4x144 values '+field, values.shape==(4, 144) and np.isfinite(values).all())
        limit = max(abs(values).max(), 1e-12)
        im = ax[i].imshow(values, interpolation='nearest', aspect='auto', origin='upper',
                          extent=(0, 24, 3.5, -.5), cmap=cmap, norm=TwoSlopeNorm(0, -limit, limit))
        ax[i].set_yticks(range(4), [d[5:] for d in DATES])
        ax[i].set_ylabel('日期')
        ax[i].set_title(f'({chr(97+i)}) {label}：4-3 − 第三问', loc='left', fontweight='bold', pad=7)
        for h in [6, 12, 18]:
            ax[i].axvline(h, color=GRAY, ls=':', lw=.7)
        for y in [.5, 1.5, 2.5]:
            ax[i].axhline(y, color='white', lw=1.4)
        cb = fig.colorbar(im, ax=ax[i], fraction=.045, pad=.025)
        cb.set_ticks([-limit, 0, limit])
        cb.set_ticklabels([f'{-limit:.2f}' if i==0 else f'{-limit:.0f}', '0', f'{limit:.2f}' if i==0 else f'{limit:.0f}'])
        hours(ax[i], False)
    hours(ax[-1])
    finish(fig, '10_q43_schedule_differences', '4-3：电价、执行购电和储能状态的差异分布',
        '以同日同段配对差异定位两问的不同，避免重复呈现两套结构相同的绝对调度曲线。',
        '四个指定日中，4-3相对第三问的电价、最终执行购电功率及段末储电量差值。蓝色表示4-3更高，橙色表示更低，白色表示接近零；各面板使用独立的对称色标，数值未裁剪，竖虚线为6、12、18点。',
        '配对差值图保留了两问在相同实际负载与光伏条件下的时段对应关系。电价、购电与储能状态的差异具有不同的时间分布，显示调度响应包含跨时段的能量转移。各指定日的初始储电量已由此前滚动执行决定，两问并不相同，因此状态差异既包含当日决策差异，也包含前期累积影响。图中比较用于描述两套已保存运行结果，不能将某一列的颜色直接解释为另一列的因果效应。',
        'date/slot完整一对一配对；每个面板576个十分钟值，不按小时平均、不平滑、不选择极端日、不使用分位截断。单位不同，三个色标独立；储电量取段末值，初始状态另见数据表。')


def tex_escape(value):
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
               '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}'}
    return ''.join(mapping.get(c, c) for c in value)


def documents():
    md = ['# 新论文图包：图注与正文描述', '',
          '本文件为新论文提供独立图文材料，图号为本图包临时编号，可按新稿章节调整。下面的“图注”和“正文描述”可直接改编使用；“取数与解释边界”用于核对。', '',
          '全部年度图统计2025年2月1日至12月31日334天；问题一为附件1典型日。第二问与4-2的初末储电量为8550/6000 kWh，第三问与4-3为6000/6000 kWh；禁止直接用跨口径总费用差宣称策略收益。', '']
    snippets, pages, sections = [], [], []
    for i, r in enumerate(RECORDS, 1):
        p = 'figures/'+r['id']
        md += [f'## 图{i}　{r["title"]}', '', f'**表达目标：** {r["purpose"]}', '',
               f'![{r["title"]}]({p}.png)', '', f'[矢量PDF]({p}.pdf) · [PNG]({p}.png)', '',
               '**图注：** '+r['caption'], '', '**正文描述：** '+r['body'], '',
               '**取数与解释边界：** '+r['method'], '',
               '**输入：** '+', '.join('`'+p+'`' for p in r['inputs']), '',
               '**绘图数据：** '+', '.join(f'[{p}]({p})' for p in r['tables']), '']
        label = 'fig:new-'+r['id']
        snippets.append('\n'.join([r'\begin{figure}[htbp]', r'\centering',
            r'\includegraphics[width=\linewidth]{figure_package/'+p+'.pdf}',
            r'\caption{'+tex_escape(r['caption'])+'}', r'\label{'+label+'}', r'\end{figure}', '',
            tex_escape(r['body']), '']))
        pages.append('\n'.join([r'\section*{图'+str(i)+'　'+tex_escape(r['title'])+'}',
            r'\begin{center}\includegraphics[width=\linewidth]{'+p+r'.pdf}\end{center}',
            r'{\small\textbf{图注：}'+tex_escape(r['caption'])+r'\par}', r'\medskip',
            r'{\small\textbf{正文描述：}'+tex_escape(r['body'])+r'\par}', r'\newpage']))
        sections.append(f'<section id="{r["id"]}"><p class="eyebrow">图 {i:02d}</p>'
            f'<h2>{html.escape(r["title"])}</h2><p class="purpose">{html.escape(r["purpose"])}</p>'
            f'<img src="{p}.png" alt="{html.escape(r["title"])}">'
            f'<p><b>图注：</b>{html.escape(r["caption"])}</p><p><b>正文描述：</b>{html.escape(r["body"])}</p>'
            f'<details><summary>取数与解释边界</summary><p>{html.escape(r["method"])}</p></details>'
            f'<a href="{p}.pdf">下载矢量 PDF</a></section>')
    (HERE/'图注与正文.md').write_text('\n'.join(md), encoding='utf-8')
    (HERE/'insert_figures.tex').write_text('% 从新论文位于paper/的主文件中引用；需要graphicx。\n'+'\n'.join(snippets), encoding='utf-8')
    preamble = r'''\documentclass[10pt,a4paper]{article}
\usepackage[UTF8,fontset=windows]{ctex}
\usepackage[margin=15mm]{geometry}
\usepackage{graphicx}
\usepackage{hyperref}
\hypersetup{hidelinks}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\begin{document}
'''
    (HERE/'figure_book.tex').write_text(preamble+'\n'.join(pages)+r'\end{document}', encoding='utf-8')
    css = '''body{margin:0;background:#f0f3f5;color:#273b49;font:16px/1.85 "Microsoft YaHei",sans-serif}
header{max-width:1000px;margin:50px auto 25px;padding:0 28px}h1{font-size:30px}h2{font-size:23px;line-height:1.4}
section{max-width:1000px;margin:24px auto;padding:28px 38px;background:white;border-radius:8px}
img{display:block;width:100%;height:auto;margin:20px auto}a{color:#28718e}.eyebrow{color:#28718e;font-weight:bold;letter-spacing:2px;margin:0}
.purpose{color:#536774}details{padding:10px 16px;background:#f5f7f8;margin:15px 0;font-size:14px}summary{cursor:pointer}
@media print{body{background:white}header{display:none}section{break-after:page;margin:0;padding:0}details,a{display:none}}'''
    (HERE/'图文预览.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>新论文图包</title>'
        '<style>'+css+'</style><header><h1>微网购电与储能调度 · 论文图包</h1>'
        '<p>十张图依次讨论时段转移、残差口径、信息更新、价格信息与跨情形差异。'
        '全部由保存结果生成，图注与正文可用于新稿。</p></header>'+''.join(sections)+'</html>', encoding='utf-8')


def main():
    (HERE/'figures').mkdir(parents=True, exist_ok=True)
    (HERE/'data').mkdir(exist_ok=True)
    setup_style(journal='general', lang='zh', use_sciplots=False)
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    font = next((f for f in ('Microsoft YaHei', 'Noto Sans CJK SC', 'SimHei') if f in available), None)
    if font is None:
        raise RuntimeError('A Chinese font is required')
    plt.rcParams.update({'font.family':font, 'font.size':8.5, 'axes.labelsize':8.5,
        'axes.titlesize':9.5, 'xtick.labelsize':8, 'ytick.labelsize':8,
        'legend.fontsize':8, 'lines.linewidth':1.15, 'axes.linewidth':.65,
        'axes.labelcolor':INK, 'text.color':INK, 'xtick.color':INK, 'ytick.color':INK,
        'figure.facecolor':'white', 'savefig.facecolor':'white', 'axes.unicode_minus':False,
        'pdf.fonttype':42, 'svg.fonttype':'none', 'timezone':'UTC'})
    warnings.filterwarnings('error', message='Glyph .* missing from font')
    os.environ.setdefault('SOURCE_DATE_EPOCH', '0')
    for make in (q1, q2, q3_value, q3_fusion, q3_dispatch, q42_value, q42_dispatch, q43_value, q43_shift):
        make()
    documents()
    for p, expected in INPUTS.items():
        check('source unchanged: '+p, digest(ROOT/p)==expected)
    assets = {p.relative_to(HERE).as_posix():digest(p)
              for folder in ('figures', 'data') for p in sorted((HERE/folder).iterdir()) if p.is_file()}
    manifest = dict(environment=dict(python=platform.python_version(), numpy=np.__version__,
        pandas=pd.__version__, matplotlib=matplotlib.__version__, font=font),
        source_sha256=INPUTS, builder_sha256=digest(Path(__file__)),
        shared_code_sha256={p:digest(ROOT/p) for p in ['common/plotting/setup_style.py','common/plotting/export_figure.py']},
        figures=RECORDS, output_sha256=assets, checks=CHECKS,
        validation_scope='Saved-result alignment, arithmetic identities, layout bounds and unchanged inputs; no model optimization rerun.')
    (HERE/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Finished: {len(RECORDS)} figures; {len(CHECKS)} checks; inputs unchanged.')


if __name__ == '__main__':
    main()
