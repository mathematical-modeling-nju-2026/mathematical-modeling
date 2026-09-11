"""Reproduce Q4-2 with common Q2 January warm-up and actual-price settlement."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time

import numpy as np
import pandas as pd

from q42_model import (HERE, BASE_DIR, RAW, REPO, Inputs, BY_NAME, T,
                       export_workbook, label)

TOTAL_COLUMNS = ('planned_cost_yuan', 'emergency_cost_yuan', 'total_cost_yuan',
                 'g_kwh', 'c_kwh', 'd_kwh', 'emergency_kwh', 'dump_kwh')


def daily_table(detail):
    by_day = detail.groupby('date', sort=False)
    daily = by_day[list(TOTAL_COLUMNS)].sum()
    daily['energy_start_kwh'] = by_day.energy_before_kwh.first()
    daily['energy_end_kwh'] = by_day.energy_after_kwh.last()
    daily['emergency_slots'] = by_day.emergency_kwh.apply(lambda x: int((x > 1e-6).sum()))
    return daily.reset_index()


def make_day(inputs, day, plan, initial, mode, data=None):
    g, c, d, energy = (plan[k][:T] for k in ('g', 'c', 'd', 'E'))
    z = g+d-c
    actual = inputs.q2.actual[day]
    emergency = np.maximum(actual-z, 0)
    price = inputs.price[day]
    frame = pd.DataFrame(dict(date=inputs.dates[day].strftime('%Y-%m-%d'), slot=np.arange(T),
        start=[label(t) for t in range(T)], end=[label(t+1) for t in range(T)],
        price_yuan_per_kwh=price, price_point_forecast=inputs.price_point[day],
        objective_price_yuan_per_kwh=inputs.q2.price if data is None else data['plan_price'][:T],
        forecast_net_kwh=inputs.q2.point[day], actual_net_kwh=actual,
        g_kwh=g, c_kwh=c, d_kwh=d, energy_before_kwh=np.r_[initial, energy[:-1]],
        energy_after_kwh=energy, z_kwh=z, emergency_kwh=emergency,
        dump_kwh=np.maximum(z-actual, 0), planned_cost_yuan=price*g,
        emergency_cost_yuan=5*price*emergency, total_cost_yuan=price*(g+5*emergency)))
    frame['strategy'] = mode
    return frame


def common_warmup(inputs):
    """Retain the already optimized Q2's feasible January policy for every mode."""
    energy = 6000.
    days = []
    for day in range(31):
        plan, _, _ = inputs.q2.solve_day(day, energy, BY_NAME['uniform56'])
        frame = make_day(inputs, day, plan, energy, 'common_q2_january')
        # Price forecasts selected after January are not January decisions.
        frame['price_point_forecast'] = np.nan
        days.append(frame)
        energy = float(plan['E'][T-1])
    detail = pd.concat(days, ignore_index=True)
    reference = json.loads((BASE_DIR/'common_january.json').read_text(encoding='utf-8'))
    actual_soc = daily_table(detail).energy_end_kwh.to_numpy()
    if not np.allclose(actual_soc, [r['energy_end_kwh'] for r in reference], atol=1e-7, rtol=0):
        raise RuntimeError('The common January warm-up changed')
    return detail, energy


def repriced_q2(inputs):
    """Hold the improved Q2's decisions fixed; change only actual settlement prices."""
    frame = pd.read_csv(BASE_DIR/'schedule_detail.csv.gz')
    if len(frame) != 334*T:
        raise ValueError('Improved Q2 output is incomplete')
    frame['objective_price_yuan_per_kwh'] = frame.price_yuan_per_kwh
    frame['price_point_forecast'] = inputs.price_point[31:].ravel()
    frame['price_yuan_per_kwh'] = inputs.price[31:].ravel()
    frame['planned_cost_yuan'] = frame.price_yuan_per_kwh*frame.g_kwh
    frame['emergency_cost_yuan'] = 5*frame.price_yuan_per_kwh*frame.emergency_kwh
    frame['total_cost_yuan'] = frame.planned_cost_yuan+frame.emergency_cost_yuan
    frame['strategy'] = 'q2_repriced'
    return frame


def save_variant(name, detail, diagnostics=None):
    folder = HERE/'variants'/name
    folder.mkdir(parents=True, exist_ok=True)
    daily = daily_table(detail)
    if diagnostics is not None:
        daily = daily.merge(pd.DataFrame(diagnostics), on='date', validate='one_to_one')
    summary = dict(name=name, days=len(daily), report_start=daily.date.iloc[0],
                   report_end=daily.date.iloc[-1], initial_energy_kwh=float(daily.energy_start_kwh.iloc[0]),
                   final_energy_kwh=float(daily.energy_end_kwh.iloc[-1]),
                   **{col: float(daily[col].sum()) for col in TOTAL_COLUMNS})
    summary['emergency_slots'] = int(daily.emergency_slots.sum())
    summary['emergency_days'] = int((daily.emergency_kwh > 1e-6).sum())
    summary['objective_assumption'] = ('Current-day prices available at 00:00; tomorrow prices forecast from history'
        if name == 'known_today_price' else 'Only historical observations available at 00:00')
    detail.to_csv(folder/'schedule_detail.csv.gz', index=False, encoding='utf-8-sig', compression='gzip')
    daily.to_csv(folder/'daily_summary.csv', index=False, encoding='utf-8-sig')
    (folder/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    export_workbook(detail, daily, folder/'result4-2.xlsx')
    return summary


def run_variant(inputs, name, initial):
    frames, diagnostics = [], []
    energy = initial
    started = time.perf_counter()
    cumulative_cost = 0.
    for day in range(31, 365):
        plan, data = inputs.solve_day(day, energy, name)
        frame = make_day(inputs, day, plan, energy, name, data)
        frames.append(frame)
        cumulative_cost += float(frame.total_cost_yuan.sum())
        diagnostics.append(dict(date=frame.date.iloc[0], sample_count=len(data['indices']),
            max_history_day=inputs.dates[int(data['indices'][-1])].strftime('%Y-%m-%d'),
            clipped_scenario_price_count=data['clipped_prices'],
            horizon_expected_cost_yuan=plan['objective'], solver_status=plan['solver_status'],
            raw_simultaneous_slots=plan['raw_overlap']))
        energy = float(plan['E'][T-1])
        if (day-31) % 60 == 0 or day == 364:
            print(f'{name:18s} {frame.date.iloc[0]} {cumulative_cost:,.2f} yuan '
                  f'{time.perf_counter()-started:.1f}s', flush=True)
    return save_variant(name, pd.concat(frames, ignore_index=True), diagnostics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--primary', choices=('joint_price', 'known_today_price'), default='joint_price')
    args = parser.parse_args()
    inputs = Inputs()
    dependencies = [BASE_DIR/'rolling_window.py', BASE_DIR/'run_experiment.py',
                    BASE_DIR/'schedule_detail.csv.gz', BASE_DIR/'summary.json',
                    REPO/'CShen'/'方案B_1439万'/'run_1439.py',
                    REPO/'C_yang'/'q2'/'q2_data.py']
    dependencies += [RAW/f'附件{i}.xlsx' for i in (1, 2, 4)]
    fingerprints = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}
    (HERE/'source_fingerprints.json').write_text(json.dumps(fingerprints, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame(inputs.training_scores).to_csv(HERE/'price_training_scores.csv', index=False, encoding='utf-8-sig')
    price_report = dict(selected_forecaster=inputs.method, selection_completed='2025-01-31',
        shape=list(inputs.price.shape), min=float(inputs.price.min()), max=float(inputs.price.max()),
        mean=float(inputs.price.mean()), missing=int(np.isnan(inputs.price).sum()),
        report_rmse=float(np.sqrt(np.mean((inputs.price[31:]-inputs.price_point[31:])**2))),
        report_mae=float(np.mean(np.abs(inputs.price[31:]-inputs.price_point[31:]))))
    (HERE/'price_data_summary.json').write_text(json.dumps(price_report, indent=2), encoding='utf-8')
    print(json.dumps(price_report, indent=2), flush=True)
    np.savez_compressed(HERE/'forecast_archive.npz', price_actual=inputs.price,
        price_point=inputs.price_point, price_tomorrow=inputs.price_tomorrow,
        price_residual=inputs.price_residual, net_point=inputs.q2.point,
        net_tomorrow=inputs.q2.tomorrow, net_residual=inputs.q2.residual)
    january, initial = common_warmup(inputs)
    january.to_csv(HERE/'january_warmup.csv.gz', index=False, encoding='utf-8-sig', compression='gzip')
    daily_table(january).to_csv(HERE/'january_summary.csv', index=False, encoding='utf-8-sig')
    if abs(initial-json.loads((BASE_DIR/'summary.json').read_text(encoding='utf-8'))['initial_energy_kwh']) > 1e-7:
        raise RuntimeError('Q2 and Q4 initial states differ')
    summaries = [save_variant('q2_repriced', repriced_q2(inputs))]
    for mode in ('mean_price', 'joint_price', 'known_today_price'):
        summaries.append(run_variant(inputs, mode, initial))
    comparison = pd.DataFrame(summaries)
    baseline = float(comparison.iloc[0].total_cost_yuan)
    comparison['saving_vs_repriced_q2_yuan'] = baseline-comparison.total_cost_yuan
    comparison['saving_percent'] = 100*comparison.saving_vs_repriced_q2_yuan/baseline
    comparison.to_csv(HERE/'comparison.csv', index=False, encoding='utf-8-sig')
    metadata = dict(primary_variant=args.primary, q2_source=str(BASE_DIR.relative_to(REPO)),
        report_period=['2025-02-01', '2025-12-31'], days=334, first_residual_index=7,
        scenario_window=56, scenario_weights='equal', horizon_days=2,
        price_forecaster=inputs.method, price_training_period=['2025-01-08', '2025-01-31'],
        price_floor=0.001, initial_energy_kwh=initial, year_end_energy_kwh=6000.,
        january_policy='Common unchanged Q2 policy, from January 1 SOC 6000; repriced but excluded from report costs.',
        price_information='Default: only days strictly before decision date. Known-today sensitivity explicitly relaxes this for prices only.',
        settlement='Actual attachment 4 price times planned kWh + 5 times actual price times emergency kWh.',
        second_day='Point net-load forecast and historical price forecast only; no second-day scenarios.',
        primary_selection='Determined by the price-information assumption, not by retrospective annual cost ranking.',
        python=sys.version)
    (HERE/'run_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    for p in dependencies:
        if hashlib.sha256(p.read_bytes()).hexdigest() != fingerprints[str(p.relative_to(REPO))]:
            raise RuntimeError(f'Source file changed: {p}')
    print(comparison[['name', 'total_cost_yuan', 'saving_vs_repriced_q2_yuan']].to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
