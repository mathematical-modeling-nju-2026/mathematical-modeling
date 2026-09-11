"""问题二：滚动日前计划 + 实现后紧急购电补救。

依赖：numpy、pandas、scipy、scikit-learn、Pillow。
运行前示例（PowerShell）：
  $env:PYTHONPATH='.../work/q2_vendor'
  python M2_E01_v1_rolling_stochastic_lp.py

设计边界：预测模型只使用目标日 0:00 前可获得的负荷和光伏历史；
当天真实曲线只用于回测结算，绝不进入当日的计划决策。
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import linprog
from sklearn.ensemble import GradientBoostingRegressor

DT = 1 / 6
ETA_C = ETA_D = 0.90
E_MIN, E_MAX, E0 = 1200.0, 10800.0, 6000.0
P_MAX = 5000.0
FLOW_CAP = P_MAX * DT
WINDOW = 84
SCENARIO_COUNT = 6
RETRAIN_EVERY = 14
CVaR_ALPHA, CVAR_WEIGHT = 0.90, 0.05
START_DAY = 31                     # 2025-02-01，1 月仅作为启动历史
TERMINAL_TARGET = 6000.0
EPS = 1e-7

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_DIR = SCRIPT_DIR.parent
PROJECT_DIR = MODEL_DIR.parents[1]
RAW = PROJECT_DIR / "01_数据与版本" / "D0_raw" / "附件"
ATTACH2 = RAW / "附件2.xlsx"
OUT = MODEL_DIR
CHART = OUT / "chart_data"
FIG = OUT / "figures"
PROJECT_FIG = PROJECT_DIR / "outputs" / "图表"


def load_data():
    load = pd.read_excel(ATTACH2, sheet_name="小区负载")
    pv = pd.read_excel(ATTACH2, sheet_name="光伏发电实际功率")
    dates = pd.to_datetime(load.iloc[:, 0]).to_numpy()
    if load.shape != (365, 145) or pv.shape != (365, 145):
        raise ValueError(f"附件 2 形状异常：负荷 {load.shape}，光伏 {pv.shape}。")
    if not np.array_equal(pd.to_datetime(pv.iloc[:, 0]).to_numpy(), dates):
        raise ValueError("负荷与光伏的日期索引不一致。")
    L = load.iloc[:, 1:].to_numpy(dtype=float) * DT
    S = pv.iloc[:, 1:].to_numpy(dtype=float) * DT
    if np.isnan(L).any() or np.isnan(S).any() or (L < 0).any() or (S < 0).any():
        raise ValueError("附件 2 存在缺失或负功率，请先处理数据。")
    return dates, L, S


def load_prices():
    p = pd.read_excel(RAW / "附件1.xlsx")
    price = p["电价"].to_numpy(float)
    if len(price) != 144 or (price < 0).any():
        raise ValueError("附件 1 的电价长度或符号异常。")
    return price


def idx(day: int, lag: int, cyclic: bool) -> int | None:
    candidate = day - lag
    if candidate >= 0:
        return candidate
    return candidate % 365 if cyclic else None


def seasonal_forecast(net: np.ndarray, day: int, window: int, cyclic: bool) -> np.ndarray:
    """可解释基线：同星期几历史曲线的指数加权季节性平均。"""
    candidates = []
    for lag in range(7, window + 1, 7):
        h = idx(day, lag, cyclic)
        if h is not None:
            candidates.append((h, math.exp(-lag / max(window / 2, 1))))
    if not candidates:
        # 严格过去数据的早期回退：最近可见日的曲线，不读取未来。
        h = idx(day, 1, cyclic)
        return net[h].copy() if h is not None else net[0].copy()
    rows = np.array([net[h] for h, _ in candidates])
    weights = np.array([w for _, w in candidates])
    return np.average(rows, axis=0, weights=weights)


def features_for_day(net, load, pv, dates, day, cyclic):
    """144 行特征；每行只读取该日之前（或显式周期代理）的信息。"""
    t = np.arange(144)
    date = pd.Timestamp(dates[day])
    dow = date.dayofweek
    doy = date.dayofyear
    def curve(lag):
        h = idx(day, lag, cyclic)
        return net[h] if h is not None else net[max(day - 1, 0)]
    lag1, lag7, lag14, lag28 = (curve(k) for k in (1, 7, 14, 28))
    history7 = [curve(k) for k in range(1, 8)]
    history14 = [curve(k) for k in range(1, 15)]
    pday = idx(day, 1, cyclic)
    pday = max(day - 1, 0) if pday is None else pday
    return np.column_stack([
        t / 143, np.sin(2 * np.pi * t / 144), np.cos(2 * np.pi * t / 144),
        np.full(144, dow / 6), np.full(144, np.sin(2 * np.pi * doy / 365)),
        np.full(144, np.cos(2 * np.pi * doy / 365)), lag1, lag7, lag14, lag28,
        np.mean(history7, axis=0), np.mean(history14, axis=0),
        np.full(144, load[pday].sum()), np.full(144, pv[pday].sum()),
    ])


def train_gbdt(net, load, pv, dates, day, window, cyclic):
    """以最近窗口的时段观测训练非线性中位数与 80% 分位数模型。"""
    if cyclic:
        train_days = [(day - k) % 365 for k in range(window, 0, -1)]
    else:
        train_days = list(range(max(28, day - window), day))
    train_days = [h for h in train_days if h != day and (cyclic or h >= 28)]
    if len(train_days) < 7:
        return None, None
    X = np.vstack([features_for_day(net, load, pv, dates, h, cyclic) for h in train_days])
    y = np.concatenate([net[h] for h in train_days])
    common = dict(n_estimators=80, learning_rate=0.07, max_depth=3,
                  min_samples_leaf=20, random_state=2026)
    median = GradientBoostingRegressor(loss="quantile", alpha=0.5, **common).fit(X, y)
    q80 = GradientBoostingRegressor(loss="quantile", alpha=0.8, **common).fit(X, y)
    return median, q80


def residual_scenarios(net, day, point_forecast, window, cyclic):
    """使用整日净负荷残差曲线，保持同一天内 144 时段误差的相关性。"""
    hist = [(day - k) % 365 for k in range(window, 0, -1)] if cyclic else list(range(max(1, day - window), day))
    curves = []
    for h in hist:
        pred_h = seasonal_forecast(net, h, window, cyclic)
        curves.append(net[h] - pred_h)
    if not curves:
        return np.zeros((1, 144))
    arr = np.asarray(curves)
    score = arr.sum(axis=1)
    grid = np.linspace(0.08, 0.92, SCENARIO_COUNT)
    chosen = []
    for q in grid:
        target = np.quantile(score, q)
        chosen.append(arr[np.argmin(np.abs(score - target))])
    scenarios = np.asarray(chosen)
    # 令场景均值与点预测对齐，避免因残差样本非零均值造成系统偏移。
    return point_forecast + scenarios - scenarios.mean(axis=0)


def solve_day(price, scenario_net, e_start, terminal_day=False):
    """在给定场景下解两阶段 LP。g,c,q,E 非前瞻；e,w 为场景补救变量。"""
    S_num, T = scenario_net.shape
    ig = slice(0, T); ic = slice(T, 2*T); iq = slice(2*T, 3*T)
    iE = slice(3*T, 4*T+1)
    ie = slice(4*T+1, 4*T+1+S_num*T)
    iw = slice(ie.stop, ie.stop+S_num*T)
    iz = iw.stop; iu = slice(iz+1, iz+1+S_num); n = iu.stop
    cobj = np.zeros(n)
    cobj[ig] = price
    for s in range(S_num):
        cobj[ie.start+s*T:ie.start+(s+1)*T] = 5*price/S_num
    cobj[ic] = 1e-6; cobj[iq] = 1e-6  # 只用于消除同时充放电的退化解
    cobj[iz] = CVAR_WEIGHT
    cobj[iu] = CVAR_WEIGHT / ((1-CVaR_ALPHA)*S_num)

    # 各场景能量平衡 + 公共储能动态 + 当前日初电量。
    Aeq = np.zeros((S_num*T + T + 1, n)); beq = np.zeros(S_num*T + T + 1)
    r = 0
    for s in range(S_num):
        for t in range(T):
            Aeq[r, ig.start+t] = 1; Aeq[r, ic.start+t] = -1; Aeq[r, iq.start+t] = 1
            Aeq[r, ie.start+s*T+t] = 1; Aeq[r, iw.start+s*T+t] = -1
            beq[r] = scenario_net[s, t]; r += 1
    for t in range(T):
        Aeq[r, iE.start+t] = -1; Aeq[r, iE.start+t+1] = 1
        Aeq[r, ic.start+t] = -ETA_C; Aeq[r, iq.start+t] = 1/ETA_D; r += 1
    Aeq[r, iE.start] = 1; beq[r] = e_start

    # CVaR：u_s >= 5*sum(p_t e_st)-zeta；年末终端库存不低于 6000 kWh。
    Aub = np.zeros((S_num + int(terminal_day), n)); bub = np.zeros(S_num + int(terminal_day))
    for s in range(S_num):
        Aub[s, ie.start+s*T:ie.start+(s+1)*T] = 5*price
        Aub[s, iz] = -1; Aub[s, iu.start+s] = -1
    if terminal_day:
        Aub[-1, iE.stop-1] = -1; bub[-1] = -TERMINAL_TARGET
    bounds = []
    bounds += [(0, None)] * T
    bounds += [(0, FLOW_CAP)] * T
    bounds += [(0, FLOW_CAP)] * T
    bounds += [(E_MIN, E_MAX)] * (T+1)
    bounds += [(0, None)] * (2*S_num*T)
    bounds += [(0, None)] + [(0, None)] * S_num
    res = linprog(cobj, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"LP 求解失败：{res.message}")
    z = res.x
    return {"g":z[ig], "c":z[ic], "q":z[iq], "E":z[iE], "expected_e":z[ie].reshape(S_num,T), "expected_w":z[iw].reshape(S_num,T), "cvar":z[iz] + z[iu].sum()/((1-CVaR_ALPHA)*S_num)}


def run_backtest(name, net, load, pv, dates, price, predictor, cyclic=False, window=WINDOW):
    """逐日回测。当天预测和场景仅依赖目标日之前的资料；真实曲线只在最后结算。"""
    e_state = E0; models = (None, None); outputs=[]; daily=[]; forecast_rows=[]
    for day in range(START_DAY, 365):
        if predictor == "gbdt" and ((day-START_DAY) % RETRAIN_EVERY == 0 or models[0] is None):
            models = train_gbdt(net, load, pv, dates, day, window, cyclic)
        base = seasonal_forecast(net, day, window, cyclic)
        if predictor == "gbdt" and models[0] is not None:
            feat = features_for_day(net, load, pv, dates, day, cyclic)
            point = models[0].predict(feat); q80 = models[1].predict(feat)
        else:
            point = base; q80 = base
        scen = residual_scenarios(net, day, point, window, cyclic)
        plan = solve_day(price, scen, e_state, terminal_day=(day == 364))
        actual = net[day]
        emergency = np.maximum(actual + plan["c"] - plan["g"] - plan["q"], 0)
        curtail = np.maximum(plan["g"] + plan["q"] - actual - plan["c"], 0)
        plan_cost = float(price @ plan["g"])
        emergency_cost = float(5 * price @ emergency)
        outputs.append({"day":day, "date":pd.Timestamp(dates[day]), "plan":plan, "point":point, "q80":q80,
                        "actual":actual, "emergency":emergency, "curtail":curtail})
        daily.append({"日期":pd.Timestamp(dates[day]), "模型":name, "计划购电费_元":plan_cost,
                      "紧急购电费_元":emergency_cost, "实际总成本_元":plan_cost+emergency_cost,
                      "计划购电量_kWh":plan["g"].sum(), "紧急购电量_kWh":emergency.sum(),
                      "紧急购电次数":int((emergency > 1e-5).sum()), "弃电量_kWh":curtail.sum(),
                      "期初储能_kWh":e_state, "期末储能_kWh":plan["E"][-1], "CVaR紧急成本_元":plan["cvar"],
                      "净负荷RMSE_kWh":float(np.sqrt(np.mean((point-actual)**2)),),
                      "净负荷MAE_kWh":float(np.mean(np.abs(point-actual))),
                      "80分位覆盖率":float(np.mean(actual <= q80))})
        forecast_rows.append({"日期":pd.Timestamp(dates[day]), "模型":name,
                              "RMSE_kWh":float(np.sqrt(np.mean((point-actual)**2))),
                              "MAE_kWh":float(np.mean(np.abs(point-actual))),
                              "Q80覆盖率":float(np.mean(actual<=q80))})
        e_state = float(plan["E"][-1])
    return outputs, pd.DataFrame(daily), pd.DataFrame(forecast_rows)


def time_labels():
    def fmt(m): return "0:00+1" if m==1440 else f"{m//60}:{m%60:02d}"
    return [f"{fmt(10*t)}-{fmt(10*(t+1))}" for t in range(144)]


def font(size):
    p = Path(r"C:\Windows\Fonts\msyh.ttc")
    return ImageFont.truetype(p, size) if p.exists() else ImageFont.load_default()


def chart(path, title, xlabels, lines, ylabel):
    W,H,L,R,T,B=1700,820,110,70,120,105
    img=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(img); f=font(22); fs=font(17); ft=font(30)
    d.text((L,28),title,font=ft,fill="#111111"); vals=np.concatenate([v for _,v,_ in lines]); lo=min(0,float(vals.min())); hi=float(vals.max()); pad=max((hi-lo)*.08,1); lo-=pad; hi+=pad
    def xy(i,v): return (L+i*(W-L-R)/max(len(xlabels)-1,1),T+(hi-v)*(H-T-B)/max(hi-lo,1e-9))
    for k in range(6):
        val=lo+(hi-lo)*k/5; y=xy(0,val)[1]; d.line((L,y,W-R,y),fill="#E5E7EB"); d.text((10,y-10),f"{val:,.0f}",font=fs,fill="#4B5563")
    d.line((L,T,L,H-B),fill="#374151",width=2); d.line((L,H-B,W-R,H-B),fill="#374151",width=2)
    lx=L
    for name,arr,color in lines:
        d.line([xy(i,float(v)) for i,v in enumerate(arr)],fill=color,width=3); d.line((lx,90,lx+35,90),fill=color,width=4); d.text((lx+42,77),name,font=f,fill="#111111"); lx+=42+d.textlength(name,font=f)+35
    for i in range(0,len(xlabels),max(1,len(xlabels)//8)):
        x=xy(i,lo)[0]; d.text((x-18,H-B+14),str(xlabels[i]),font=fs,fill="#4B5563")
    d.text((L,H-55),"日期",font=f,fill="#111111"); d.text((12,T-35),ylabel,font=f,fill="#111111"); img.save(path)


def main():
    for p in (CHART, FIG, PROJECT_FIG): p.mkdir(parents=True, exist_ok=True)
    dates,L,S=load_data(); price=load_prices(); net=L-S
    # W 敏感性：严格过去数据的可解释基线预测误差，不以该表单独挑选主模型。
    win_rows=[]
    for W in (14,28,56,84,112,334):
        errs=[]
        for d in range(START_DAY,365): errs.append(seasonal_forecast(net,d,W,False)-net[d])
        a=np.vstack(errs); win_rows.append({"窗口天数":W,"严格过去RMSE_kWh":float(np.sqrt(np.mean(a*a))),"严格过去MAE_kWh":float(np.mean(np.abs(a)))})
    window_df=pd.DataFrame(win_rows)

    # 主回测为严格过去信息的非线性分位数预测；基线提供实际结算成本对照。
    base_out, base_daily, base_pred = run_backtest("同星期加权基线",net,L,S,dates,price,"baseline",False)
    main_out, main_daily, main_pred = run_backtest("GBDT分位数主模型",net,L,S,dates,price,"gbdt",False)
    # 周期延拓敏感性只检验预测误差，明确它使用年末作为上一年度代理，不能当作严格实时结果。
    cyc_err=[]
    for d in range(START_DAY,365): cyc_err.append(seasonal_forecast(net,d,WINDOW,True)-net[d])
    strict_err=[]
    for d in range(START_DAY,365): strict_err.append(seasonal_forecast(net,d,WINDOW,False)-net[d])
    cycle_compare=pd.DataFrame([{ "设定":"严格仅过去数据", "RMSE_kWh":float(np.sqrt(np.mean(np.vstack(strict_err)**2))), "MAE_kWh":float(np.mean(np.abs(np.vstack(strict_err))) )}, {"设定":"年周期延拓代理", "RMSE_kWh":float(np.sqrt(np.mean(np.vstack(cyc_err)**2))), "MAE_kWh":float(np.mean(np.abs(np.vstack(cyc_err))) )}])
    compare=pd.concat([base_daily,main_daily]).groupby("模型",as_index=False).agg({"实际总成本_元":"sum","计划购电费_元":"sum","紧急购电费_元":"sum","紧急购电量_kWh":"sum","紧急购电次数":"sum","弃电量_kWh":"sum","净负荷RMSE_kWh":"mean","净负荷MAE_kWh":"mean","80分位覆盖率":"mean"})
    compare["平均每次紧急购电量_kWh"]=compare["紧急购电量_kWh"]/compare["紧急购电次数"].replace(0,np.nan)
    main_daily["季度"]="Q"+main_daily["日期"].dt.quarter.astype(str)
    season=main_daily.groupby("季度",as_index=False).agg({"实际总成本_元":"sum","紧急购电量_kWh":"sum","紧急购电次数":"sum","弃电量_kWh":"sum","净负荷RMSE_kWh":"mean"})

    labels=time_labels(); plan_rows=[]; storage_rows=[]; emerg_rows=[]; specified=[]; detail_rows=[]
    specified_dates={"2025-03-20","2025-06-21","2025-09-23","2025-12-21"}
    for out in main_out:
        dte=out["date"]; plan=out["plan"]; daystr=dte.strftime("%Y-%m-%d")
        plan_rows.append([dte,*plan["g"].tolist()])
        for b in range(6):
            a,z=24*b,24*(b+1); storage_rows.append({"日期":dte,"时间段":f"{4*b}:00-{4*(b+1)}:00","充电量_kWh":plan["c"][a:z].sum(),"放电量_kWh":plan["q"][a:z].sum(),"时段初储能_kWh":plan["E"][a],"时段末储能_kWh":plan["E"][z]})
        e=out["emergency"]; active=e>1e-5; t=0
        # 全时段审计数据：真实曲线仅用于计划完成后的结算与校验，不参与日前决策。
        for t in range(144):
            balance=plan["g"][t]+plan["q"][t]+e[t]-out["actual"][t]-plan["c"][t]-out["curtail"][t]
            detail_rows.append({"日期":dte,"时段":labels[t],"计划购电量_kWh":plan["g"][t],
                                "充电量_kWh":plan["c"][t],"放电量_kWh":plan["q"][t],
                                "时段初储能_kWh":plan["E"][t],"时段末储能_kWh":plan["E"][t+1],
                                "真实净负荷_kWh":out["actual"][t],"紧急购电量_kWh":e[t],
                                "弃电量_kWh":out["curtail"][t],"能量平衡残差_kWh":balance})
        t=0  # 审计 for 循环结束后，重新从 0:00 扫描并压缩全部紧急购电区间。
        while t<144:
            if not active[t]: t+=1; continue
            start=t; total=0.0
            while t<144 and active[t]: total+=e[t]; t+=1
            emerg_rows.append({"日期":dte,"紧急购电时间段":f"{labels[start].split('-')[0]}-{labels[t-1].split('-')[1]}","紧急购电量_kWh":total})
        if daystr in specified_dates:
            for t in range(144): specified.append({"日期":dte,"时段":labels[t],"计划购电量_kWh":plan["g"][t],"充电量_kWh":plan["c"][t],"放电量_kWh":plan["q"][t],"时段初储能_kWh":plan["E"][t],"紧急购电量_kWh":e[t]})
    plan_df=pd.DataFrame(plan_rows,columns=["日期",*labels]); storage_df=pd.DataFrame(storage_rows); emergency_df=pd.DataFrame(emerg_rows); specified_df=pd.DataFrame(specified); detail_df=pd.DataFrame(detail_rows)
    plan_df.to_csv(CHART/"result2_计划购电量完整.csv",index=False,encoding="utf-8-sig")
    storage_df.to_csv(CHART/"result2_充放电量完整.csv",index=False,encoding="utf-8-sig")
    emergency_df.to_csv(CHART/"result2_紧急购电量汇总.csv",index=False,encoding="utf-8-sig")
    specified_df.to_csv(CHART/"result2_指定日期明细.csv",index=False,encoding="utf-8-sig")
    detail_df.to_csv(CHART/"result2_全时段回测审计明细.csv",index=False,encoding="utf-8-sig")
    compare.to_csv(CHART/"模型实际结算成本对比.csv",index=False,encoding="utf-8-sig")
    window_df.to_csv(CHART/"窗口长度预测对照.csv",index=False,encoding="utf-8-sig")
    cycle_compare.to_csv(CHART/"周期性假设对照.csv",index=False,encoding="utf-8-sig")
    season.to_csv(CHART/"季度表现.csv",index=False,encoding="utf-8-sig")
    main_daily.to_csv(CHART/"主模型逐日结算.csv",index=False,encoding="utf-8-sig")
    # 自动校验：数据索引、10 分钟映射、单位上限、储能边界与跨日连续性、结算能量平衡。
    state_starts=detail_df.groupby("日期",sort=True)["时段初储能_kWh"].first().to_numpy()
    state_ends=detail_df.groupby("日期",sort=True)["时段末储能_kWh"].last().to_numpy()
    audit={"回测天数":int(plan_df.shape[0]),"每日时段数_目标":144,"每日时段数全部合格":bool((detail_df.groupby("日期").size()==144).all()),
           "计划购电非负":bool((detail_df["计划购电量_kWh"]>=-1e-7).all()),
           "充放电上限合格":bool(((detail_df["充电量_kWh"]<=FLOW_CAP+1e-6)&(detail_df["放电量_kWh"]<=FLOW_CAP+1e-6)).all()),
           "储能下界_kWh":float(detail_df["时段初储能_kWh"].min()),"储能上界_kWh":float(detail_df["时段末储能_kWh"].max()),
           "最大跨日连续误差_kWh":float(np.max(np.abs(state_ends[:-1]-state_starts[1:]))),
           "最大实际能量平衡残差_kWh":float(np.abs(detail_df["能量平衡残差_kWh"]).max()),
           "年末储能_kWh":float(state_ends[-1])}
    if not (audit["回测天数"]==334 and audit["每日时段数全部合格"] and audit["计划购电非负"] and audit["充放电上限合格"] and audit["储能下界_kWh"]>=E_MIN-1e-6 and audit["储能上界_kWh"]<=E_MAX+1e-6 and audit["最大跨日连续误差_kWh"]<=1e-6 and audit["最大实际能量平衡残差_kWh"]<=1e-6 and audit["年末储能_kWh"]>=TERMINAL_TARGET-1e-6):
        raise RuntimeError(f"自动校验失败：{audit}")
    (OUT/"validation_M2_E01_v1.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    # 图表仅汇总日度或季度信息；逐时段原始点均在 CSV 中。
    ds=main_daily["日期"].dt.strftime("%m-%d").tolist()
    chart(FIG/"fig_M2_E01_v1_逐日成本对比.png","图 1 两类预测策略的逐日实际结算成本",ds,[("同星期基线",base_daily["实际总成本_元"].to_numpy(),"#4472C4"),("GBDT主模型",main_daily["实际总成本_元"].to_numpy(),"#ED7D31")],"实际成本 (元)")
    chart(FIG/"fig_M2_E01_v1_季度紧急购电量.png","图 2 主模型季度紧急购电量",season["季度"].tolist(),[("紧急购电量",season["紧急购电量_kWh"].to_numpy(),"#70AD47")],"紧急购电量 (kWh)")
    chart(FIG/"fig_M2_E01_v1_储能轨迹.png","图 3 主模型跨日储能期末轨迹",ds,[("期末储能",main_daily["期末储能_kWh"].to_numpy(),"#5B9BD5")],"储能电量 (kWh)")
    for f in FIG.glob("fig_M2_E01_v1_*.png"): shutil.copy2(f,PROJECT_FIG/f.name)
    metrics={"主模型实际结算总成本_元":float(main_daily["实际总成本_元"].sum()),"主模型计划购电费_元":float(main_daily["计划购电费_元"].sum()),"主模型紧急购电费_元":float(main_daily["紧急购电费_元"].sum()),"主模型紧急购电量_kWh":float(main_daily["紧急购电量_kWh"].sum()),"主模型紧急购电次数":int(main_daily["紧急购电次数"].sum()),"主模型弃电量_kWh":float(main_daily["弃电量_kWh"].sum()),"年末储能_kWh":float(main_daily.iloc[-1]["期末储能_kWh"]),"基线实际结算总成本_元":float(base_daily["实际总成本_元"].sum())}
    (OUT/"summary_metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8")
    # 题目表 1、表 2、表 3 的可直接引用版；官方模板仍保留完整全年数据。
    selected_plan=[]
    for dte in sorted(pd.to_datetime(list(specified_dates))):
        r=plan_df.loc[plan_df["日期"]==dte].iloc[0]
        selected_plan.append({"日期":dte.strftime("%Y-%m-%d"), **{labels[i]:float(r[labels[i]]) for i in (60,72,84,96,108,120)}, "全天购电量_kWh":float(r[labels].sum()), "全天购电费_元":float(price@r[labels].to_numpy(float))})
    selected_plan_df=pd.DataFrame(selected_plan)
    selected_plan_df.to_csv(CHART/"表1_指定日期计划购电.csv",index=False,encoding="utf-8-sig")
    storage_df[storage_df["日期"].isin(pd.to_datetime(list(specified_dates)))].to_csv(CHART/"表2_指定日期充放电.csv",index=False,encoding="utf-8-sig")
    emergency_df[emergency_df["日期"].isin(pd.to_datetime(list(specified_dates)))].to_csv(CHART/"表3_指定日期紧急购电.csv",index=False,encoding="utf-8-sig")
    comp=compare.set_index("模型")
    md=f"""# 问题二滚动随机日前调度复盘

## 结论

主模型以严格历史信息训练 GBDT 分位数预测，在 2025-02-01 至 2025-12-31 的逐日回测中，实际结算总成本为 {metrics['主模型实际结算总成本_元']:,.2f} 元，其中计划购电费 {metrics['主模型计划购电费_元']:,.2f} 元、紧急购电费 {metrics['主模型紧急购电费_元']:,.2f} 元。紧急购电总量为 {metrics['主模型紧急购电量_kWh']:,.2f} kWh，共发生 {metrics['主模型紧急购电次数']} 个十分钟时段；年末储能为 {metrics['年末储能_kWh']:,.2f} kWh，满足终端不低于 6000 kWh 的约束。

## 两阶段模型

第一阶段在每日 0:00 决定计划购电 g、充电 c、放电 q 与储能轨迹 E；第二阶段的场景变量 e 和 w 分别表示紧急购电与弃电。以净负荷 N=(L-S)Δt 表示时，场景能量平衡为 g_t+q_t+e_st=N_st+c_t+w_st。因为 g、c、q 与 E 不随场景改变，所以它们是非前瞻日前决策；e、w 在真实曲线实现后补足缺口或吸收剩余。没有引入售电变量。

目标函数由计划购电费、期望紧急购电费和紧急购电成本 CVaR 的小权重项构成。CVaR 项抑制少数高缺口天气日的尾部损失。所有预测输出和场景曲线在 LP 求解前均已固定，因此非线性 GBDT 不改变第二阶段优化问题的线性结构。

## 预测、场景与信息边界

可解释基线为同星期几历史曲线的指数加权季节性平均。主模型为梯度提升分位数回归，使用日内时刻、星期几、年内日期、前 1/7/14/28 天同刻净负荷、7/14 天滚动均值、前一日总负荷和总光伏等特征。没有天气预报时，不宣称可准确预知阴晴，而是从完整历史日净负荷残差曲线中挑选六个分位场景；每条场景保留 144 个时段的相关误差结构。

主结果严格只使用过去数据。另提供年周期延拓敏感性对照：它把年末相应日视作上一年度同季节代理，可能改善冷启动样本但带有强周期性假设，绝不可视为当天真实已知信息。窗口长度 14、28、56、84、112 和扩展窗口的预测误差见 `窗口长度预测对照.csv`；最终模型比较以实际结算总成本、紧急购电量和次数为主，而非仅以 RMSE 选优。

## 储能与终端处理

储能跨日连续：下一日 0:00 储能等于前一日 24:00 储能；未强制每日回到日初电量。为避免年末无价值地耗尽储能，只在 12 月 31 日施加 E_year_end≥6000 kWh。该终端假设会使年末计划保留库存；若改变目标值，应进行敏感性检验。

## 输出与核验

所有功率均乘以 Δt=1/6 转为 kWh；单时段充放电上限均为 833.33 kWh；储能保持在 1200 至 10800 kWh。脚本会校验附件索引、144 时段映射、缺失值、功率平衡、储能边界、非负购电和年末储能，并将数值结果写入 `validation_M2_E01_v1.json`。`result2_计划购电量完整.csv`、`result2_充放电量完整.csv`、`result2_紧急购电量汇总.csv` 是写入官方 result2 模板前的可审计数据源；`表1_指定日期计划购电.csv`、`表2_指定日期充放电.csv`、`表3_指定日期紧急购电.csv` 为题目三张指定格式表的摘录。
"""
    (OUT/"summary_M2_E01_v1_滚动随机日前调度.md").write_text(md,encoding="utf-8")
    (OUT/"notes_for_paper.md").write_text(md,encoding="utf-8")
    (OUT/"run_log.md").write_text("# 运行日志\n\n- 模型：M2_E01_v1 滚动随机日前调度\n- 数据：附件 1 固定电价，附件 2 逐日实际负荷与光伏。\n- 主设定：严格过去信息，84 日窗口，6 条完整日残差场景，GBDT 分位数预测。\n- 结算：计划购电费 + 5 倍紧急购电费；不允许售电。\n- 已通过自动索引、单位、边界、能量平衡和终端库存校验。\n",encoding="utf-8")
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
