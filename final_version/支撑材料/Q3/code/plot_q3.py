"""Recreate publication plots from the saved, verified CSV files."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

# Keep plotting bound to this question even if q3_data from another branch was
# imported earlier in the same Python process.
HERE = Path(__file__).resolve().parents[1] / 'results'


def main():
    available={f.name for f in font_manager.fontManager.ttflist}
    font=next((x for x in ('Microsoft YaHei','SimHei','Noto Sans CJK SC') if x in available), 'DejaVu Sans')
    plt.rcParams.update({'font.family':font,'axes.unicode_minus':False,'font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    out=HERE/'figures'; out.mkdir(exist_ok=True)
    def save(fig,name):
        fig.savefig(out/(name+'.png'),dpi=320,bbox_inches='tight')
        fig.savefig(out/(name+'.pdf'),bbox_inches='tight')
        plt.close(fig)
    comp=pd.read_csv(HERE/'comparison.csv')
    names={'B_aligned':'方案B同口径','only_0':'仅0点预报','at_0_6':'0、6点',
           'at_0_6_12':'0、6、12点','all':'0、6、12、18点'}
    labels=[names[m] for m in comp['mode']]
    fig,axs=plt.subplots(1,2,figsize=(11,4.0),layout='constrained')
    axs[0].scatter(labels,comp.total_cost_yuan/1e4,s=90,
                   c=['#9A9FA8','#80A7C6','#5596B4','#32748E','#E09D49'],zorder=3)
    for i,value in enumerate(comp.total_cost_yuan/1e4):
        axs[0].annotate(f'{value:.2f}',(i,value),xytext=(0,9),textcoords='offset points',ha='center')
    axs[0].set(ylabel='购电总费用（万元）',title='第三问：固定电价下的费用比较')
    axs[0].set_ylim(comp.total_cost_yuan.min()/1e4-8,comp.total_cost_yuan.max()/1e4+10)
    axs[0].set_xlim(-.5,len(labels)-.5)
    axs[0].grid(axis='y',alpha=.2)
    axs[0].tick_params(axis='x',labelrotation=20)
    bars=axs[1].bar(labels,comp.emergency_kwh/1e4,color=['#9A9FA8','#80A7C6','#5596B4','#32748E','#E09D49'])
    axs[1].bar_label(bars,fmt='%.2f',padding=4)
    axs[1].set(ylabel='紧急购电量（万kWh）',title='降低费用与控制供电缺口')
    axs[1].tick_params(axis='x',labelrotation=20)
    save(fig,'cost_comparison')

    detail=pd.read_csv(HERE/'schedule_detail.csv')
    fig,axs=plt.subplots(4,3,figsize=(13,10),sharex=True,layout='constrained')
    fig.suptitle('第三问：固定电价下的购电与储能调度')
    for row,date in enumerate(('2025-03-20','2025-06-21','2025-09-23','2025-12-21')):
        g=detail[detail.date==date]; x=(g.slot.to_numpy()+1)/6
        a,b,c=axs[row]
        a.plot(x,g.original_kwh*6,label='0点计划',color='#32748E',lw=1.1)
        a.plot(x,g.adjusted_kwh*6,label='调整后',color='#DC913C',lw=1.1,alpha=.9)
        a.set_ylabel(date+'\n功率（kW）')
        b.fill_between(x,g.charge_kwh*6,0,color='#5596B4',alpha=.8,label='充电')
        b.fill_between(x,-g.discharge_kwh*6,0,color='#DC913C',alpha=.8,label='放电')
        b.set_ylabel('储能功率（kW）')
        c.plot(np.r_[0,x],np.r_[g.iloc[0].energy_before_kwh,g.energy_after_kwh],color='#557B59',label='储电量')
        c.axhline(1200,color='#999999',ls='--',lw=.8);c.axhline(10800,color='#999999',ls='--',lw=.8)
        c.set(ylim=(600,11400),ylabel='储电量（kWh）')
        for ax in (a,b,c):
            for h in (6,12,18): ax.axvline(h,color='#888888',lw=.7,ls=':',alpha=.6)
            ax.set(xlim=(0,24),xticks=[0,6,12,18,24]);ax.grid(axis='y',alpha=.15)
        if row==0:
            a.set_title('购电计划随预报更新');b.set_title('充放电按下一执行段落实');c.set_title('跨时段储能衔接')
            for ax in (a,b,c):ax.legend(loc='upper right',fontsize=8)
    for ax in axs[-1]:ax.set_xlabel('时刻（小时）')
    save(fig,'target_dispatch')

    diag=pd.read_csv(HERE/'forecast_diagnostics.csv')
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    avg=diag.groupby('issue_hour')[['history_mae_kw','external_mae_kw','fusion_mae_kw']].mean()
    x=np.arange(4)
    for i,(col,name,color) in enumerate(zip(avg.columns,['历史预测','发布预报','在线融合'],['#9A9FA8','#80A7C6','#E09D49'])):
        axs[0].bar(x+(i-1)*.24,avg[col],width=.24,label=name,color=color)
    axs[0].set(xticks=x,xticklabels=['0—6时','6—12时','12—18时','18—24时'],ylabel='光伏预测MAE（kW）',title='各次发布后六小时的预测误差')
    axs[0].legend()
    for h in (0,6,12,18):
        g=diag[diag.issue_hour==h]
        axs[1].plot(pd.to_datetime(g.date),g.alpha_next_6h,label=f'{h}点',lw=1)
    axs[1].set(ylim=(-.03,1.06),ylabel='发布预报权重',title='融合权重仅由既往已验证误差决定')
    axs[1].legend(ncol=4,loc='upper center',bbox_to_anchor=(.5,-.25),frameon=False)
    axs[1].tick_params(axis='x',labelrotation=25)
    save(fig,'forecast_fusion')
    print('Saved PNG and PDF:',out)


if __name__=='__main__':main()
