"""Question 4-2: causal variable-price extension of the improved question 2.

Only the objective's prices change; the load/PV forecast, historical net-load
scenarios, physical constraints, and two-day horizon retain their Q2 meanings.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys

import numpy as np
import openpyxl
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

HERE = Path(__file__).resolve().parents[1] / "results"
REPO = HERE.parents[2]
BASE_DIR = REPO / 'Q2' / 'results'
RAW = REPO / 'data' / '附件'
sys.path.insert(0, str(BASE_DIR.parent / "code"))
from rolling_window import Inputs as Q2Inputs, BY_NAME, base  # noqa: E402
from run_experiment import export_workbook, label  # noqa: E402

T, DT = 144, 1 / 6
PRICE_FLOOR = 0.001
FORECASTERS = ('previous_day', 'mean7', 'profile7_lastlevel', 'weekday4')


def read_prices():
    book = openpyxl.load_workbook(RAW / '附件4.xlsx', read_only=True, data_only=True)
    rows = list(book.active.values)
    book.close()
    expected = [(i // 6, i % 6 * 10) for i in range(1, 144)]
    actual = [(v.hour, v.minute) for v in rows[0][1:144]]
    if actual != expected or rows[0][144] != '0:00+1':
        raise ValueError('Attachment 4 time headers do not represent interval endpoints')
    dates = [r[0] for r in rows[1:]]
    price = np.asarray([r[1:145] for r in rows[1:]], float)
    if price.shape != (365, T) or not np.isfinite(price).all() or (price <= 0).any():
        raise ValueError('Expected 365 x 144 finite, positive prices')
    return dates, price


def price_forecast(price, target_day, cutoff, method, fallback):
    """Use observations strictly before cutoff, including for tomorrow's forecast."""
    if not 0 <= cutoff <= target_day:
        raise ValueError('Invalid forecast information boundary')
    if cutoff == 0:
        return np.asarray(fallback).copy()
    historic = price[:cutoff]
    if method == 'previous_day':
        value = historic[-1]
    elif method == 'mean7':
        value = historic[-7:].mean(axis=0)
    elif method == 'profile7_lastlevel':
        value = historic[-7:].mean(axis=0) + historic[-1].mean() - historic[-7:].mean()
    elif method == 'weekday4':
        indices = [target_day - 7 * j for j in range(1, 5)
                   if 0 <= target_day - 7 * j < cutoff]
        value = price[indices].mean(axis=0) if indices else historic[-7:].mean(axis=0)
    else:
        raise ValueError(method)
    return np.maximum(value, PRICE_FLOOR)


def select_forecaster(price, fallback):
    """Select once on January 8-31, before the February-December reporting period."""
    rows = []
    for method in FORECASTERS:
        errors = np.array([price[d] - price_forecast(price, d, d, method, fallback)
                           for d in range(7, 31)])
        rows.append(dict(method=method, training_start='2025-01-08',
                         training_end='2025-01-31', days=24,
                         rmse=float(np.sqrt(np.mean(errors ** 2))),
                         mae=float(np.mean(np.abs(errors)))))
    return min(rows, key=lambda r: r['rmse'])['method'], rows


class Inputs:
    def __init__(self, price=None, load=None, pv=None):
        self.q2 = Q2Inputs(load=load, pv=pv)
        dates, actual_price = read_prices()
        if dates != self.q2.dates:
            raise ValueError('Dates in attachments 2 and 4 differ')
        self.dates = dates
        self.price = actual_price if price is None else np.asarray(price, float)
        if self.price.shape != (365, T) or not np.isfinite(self.price).all() or (self.price <= 0).any():
            raise ValueError('Prices must be finite and positive')
        self.method, self.training_scores = select_forecaster(self.price, self.q2.price)
        self.price_point = np.array([price_forecast(self.price, d, d, self.method, self.q2.price)
                                     for d in range(365)])
        self.price_tomorrow = np.array([price_forecast(self.price, d+1, d, self.method, self.q2.price)
                                        for d in range(364)])
        self.price_residual = self.price - self.price_point

    def planning_data(self, day, mode):
        scenarios, weights, indices = self.q2.scenario_data(day, BY_NAME['uniform56'], first_residual=7)
        if day < 31:
            raise ValueError('Q4 price forecaster is selected on January; report starts February 1')
        raw_price_scenarios = self.price_point[day] + self.price_residual[indices]
        price_scenarios = np.maximum(raw_price_scenarios, PRICE_FLOOR)
        price_mean = weights @ price_scenarios
        if mode == 'mean_price':
            price_scenarios = np.broadcast_to(price_mean, scenarios.shape).copy()
        elif mode == 'known_today_price':
            price_mean = self.price[day].copy()
            price_scenarios = np.broadcast_to(price_mean, scenarios.shape).copy()
        elif mode != 'joint_price':
            raise ValueError(mode)
        net_plan = self.q2.point[day].copy()
        plan_price = price_mean.copy()
        if day < 364:
            net_plan = np.r_[net_plan, self.q2.tomorrow[day]]
            plan_price = np.r_[plan_price, self.price_tomorrow[day]]
        return dict(net_plan=net_plan, net_scenarios=scenarios, weights=weights,
                    plan_price=plan_price, scenario_price=price_scenarios,
                    indices=indices, clipped_prices=int((raw_price_scenarios < PRICE_FLOOR).sum()))

    def solve_day(self, day, energy, mode):
        data = self.planning_data(day, mode)
        plan = solve_horizon(data['net_plan'], data['net_scenarios'], data['weights'],
                             data['plan_price'], data['scenario_price'], energy,
                             6000. if day == 364 else energy)
        return plan, data


@lru_cache(maxsize=64)
def matrices(K, S):
    """Price-independent LP structure, cached for repeated daily solves."""
    n = 4 * K + S * T
    er, ec, ev = [], [], []
    for k in range(K):
        er.extend([k] * 3)
        ec.extend([3*K+k, K+k, 2*K+k])
        ev.extend([1., -.9, 1/.9])
        if k:
            er.append(k); ec.append(3*K+k-1); ev.append(-1.)
    er.append(K); ec.append(4*K-1); ev.append(1.)
    aeq = coo_matrix((ev, (er, ec)), shape=(K+1, n)).tocsr()
    ur, uc, uv = [], [], []
    for k in range(K):
        ur.extend([k] * 3); uc.extend([k, K+k, 2*K+k]); uv.extend([-1., 1., -1.])
    for s in range(S):
        for t in range(T):
            row = K+s*T+t
            ur.extend([row] * 4)
            uc.extend([t, K+t, 2*K+t, 4*K+s*T+t])
            uv.extend([-1., 1., -1., -1.])
    aub = coo_matrix((uv, (ur, uc)), shape=(K+S*T, n)).tocsr()
    bounds = [(0., None)]*K + [(0., 5000/6)]*(2*K) + [(1200., 10800.)]*K + [(0., None)]*(S*T)
    return aeq, aub, bounds


def solve_horizon(net_plan, net_scenarios, weights, plan_price, scenario_price, initial, terminal):
    """Expected planned cost + expected 5x-price emergency recourse, sparse LP."""
    K = len(net_plan)
    S = len(weights)
    if K not in (T, 2*T) or net_scenarios.shape != (S, T) or scenario_price.shape != (S, T):
        raise ValueError('Invalid LP dimensions')
    if np.any(plan_price <= 0) or np.any(scenario_price <= 0) or np.any(weights < 0) or not np.isclose(weights.sum(), 1):
        raise ValueError('Positive prices and normalized nonnegative probabilities required')
    objective = np.r_[plan_price, np.zeros(3*K), (5*weights[:, None]*scenario_price).ravel()]
    aeq, aub, bounds = matrices(K, S)
    beq = np.zeros(K+1); beq[0] = initial; beq[-1] = terminal
    result = linprog(objective, A_ub=aub, b_ub=-np.r_[net_plan, net_scenarios.ravel()],
                     A_eq=aeq, b_eq=beq, bounds=bounds, method='highs')
    if not result.success:
        raise RuntimeError(result.message)
    g, c, d, energy = [result.x[i*K:(i+1)*K].copy() for i in range(4)]
    raw_overlap = int(((c > 1e-7) & (d > 1e-7)).sum())
    # Same SOC-preserving projection as Q2. With free surplus disposal and
    # positive emergency prices, increasing supply cannot increase cost.
    overlap = np.minimum(c, d/.81)
    c -= overlap; d -= .81*overlap
    c[np.abs(c) < 1e-9] = 0.; d[np.abs(d) < 1e-9] = 0.
    z = g+d-c
    emergency = np.maximum(net_scenarios-z[:T], 0.)
    projected_objective = float(plan_price@g + np.sum(5*weights[:, None]*scenario_price*emergency))
    if abs(projected_objective-result.fun) > 1e-4:
        raise RuntimeError('SOC-preserving projection changed the LP optimum beyond tolerance')
    return dict(g=g, c=c, d=d, E=energy, z=z, objective=projected_objective,
                raw_overlap=raw_overlap, solver_status=int(result.status))
