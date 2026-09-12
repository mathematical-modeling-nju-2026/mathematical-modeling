"""Analytical, Q2-reduction and future-information tests for Q4-2."""
from __future__ import annotations

import json
import numpy as np

from q42_model import HERE, Inputs, solve_horizon, base, T


def main():
    inputs = Inputs()
    reports = {}
    # The costly-scarcity scenario changes which net-load quantile to cover.
    # Identical prices and loads across time rule out useful storage arbitrage.
    analytical = []
    weights = np.array([.5, .5])
    net = np.array([np.full(T, 100.), np.full(T, 200.)])
    for scenario_prices, expected in [([2., .1], 18720.), ([.1, 2.], 30240.)]:
        prices = np.repeat(np.array(scenario_prices)[:, None], T, axis=1)
        plan = solve_horizon(np.full(T, 100.), net, weights, weights@prices, prices, 6000., 6000.)
        error = abs(plan['objective']-expected)
        analytical.append(dict(scenario_prices=scenario_prices, expected_cost=expected,
                               computed_cost=plan['objective'], error=error, pass_check=error < 1e-5))
    reports['analytical_price_net_dependence'] = analytical
    data = inputs.planning_data(151, 'joint_price')
    common_price = np.tile(inputs.q2.price, 2)
    repeated_price = np.broadcast_to(inputs.q2.price, data['net_scenarios'].shape).copy()
    ours = solve_horizon(data['net_plan'], data['net_scenarios'], data['weights'],
                         common_price, repeated_price, 8550., 8550.)
    original = base.solve_horizon(data['net_plan'], data['net_scenarios'], data['weights'],
                                  common_price, 8550., 8550.)
    original_cost = common_price@original['g'] + np.sum(5*data['weights'][:,None]*repeated_price*
                         np.maximum(data['net_scenarios']-original['z'][:T], 0))
    error = float(abs(ours['objective']-original_cost))
    reports['constant_price_reduces_to_q2'] = dict(objective_difference=error, pass_check=error < 1e-5)
    perturbations = []
    for day in (31, 151, 333):
        changed_price = inputs.price.copy(); changed_price[day:] = changed_price[day:]*1.35+.07
        changed_load = inputs.q2.load.copy(); changed_load[day:] += 1234.
        changed_pv = inputs.q2.pv.copy(); changed_pv[day:] *= .2
        changed = Inputs(price=changed_price, load=changed_load, pv=changed_pv)
        a = inputs.planning_data(day, 'joint_price')
        b = changed.planning_data(day, 'joint_price')
        changes = {key: float(np.max(np.abs(a[key]-b[key]))) for key in
                   ('net_plan', 'net_scenarios', 'weights', 'plan_price', 'scenario_price', 'indices')}
        first, _ = inputs.solve_day(day, 8550., 'joint_price')
        second, _ = changed.solve_day(day, 8550., 'joint_price')
        changes['decisions'] = max(float(np.max(np.abs(first[k]-second[k]))) for k in ('g','c','d','E'))
        passed = inputs.method == changed.method and max(changes.values()) < 1e-9
        perturbations.append(dict(day=day, date=inputs.dates[day].strftime('%Y-%m-%d'),
                                  max_changes=changes, forecaster_unchanged=inputs.method==changed.method,
                                  pass_check=passed))
        print('Future perturbation', day, passed, flush=True)
    reports['future_perturbations'] = perturbations
    # Even the known-today contrast cannot read tomorrow's actual prices.
    day = 151
    changed_price = inputs.price.copy(); changed_price[day+1:] *= 2
    changed = Inputs(price=changed_price)
    a, _ = inputs.solve_day(day, 8550., 'known_today_price')
    b, _ = changed.solve_day(day, 8550., 'known_today_price')
    difference = max(float(np.max(np.abs(a[k]-b[k]))) for k in ('g','c','d','E'))
    reports['known_today_cannot_read_tomorrow'] = dict(max_decision_change=difference, pass_check=difference < 1e-9)
    reports['pass_check'] = (all(r['pass_check'] for r in analytical+perturbations)
        and reports['constant_price_reduces_to_q2']['pass_check']
        and reports['known_today_cannot_read_tomorrow']['pass_check'])
    (HERE/'information_verification.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(reports, indent=2))
    if not reports['pass_check']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
