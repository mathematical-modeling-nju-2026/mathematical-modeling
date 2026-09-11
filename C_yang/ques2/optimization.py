"""Q2 fixed day-ahead battery actions, scenario emergency recourse, linear program.

All power inputs must first be converted to kWh. Net load may be negative.
The horizon may be 144 or 288 intervals; only the first day is executed.
"""
from dataclasses import dataclass, asdict
from time import perf_counter

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, diags, eye, hstack, kron


@dataclass(frozen=True)
class Parameters:
    dt_hours: float = 1/6
    eta_charge: float = 0.9
    eta_discharge: float = 0.9
    power_max_kw: float = 5000.0
    energy_min_kwh: float = 1200.0
    energy_max_kwh: float = 10800.0
    initial_energy_kwh: float = 6000.0
    reference_terminal_kwh: float = 6000.0
    emergency_multiplier: float = 5.0
    scenario_lookback: int = 28


PARAM = Parameters()


def empirical_quantile(values, weights, probability=0.8):
    """Inverse empirical CDF, independently in each column; never interpolate."""
    order = np.argsort(values, axis=0, kind="stable")
    sorted_values = np.take_along_axis(values, order, axis=0)
    cumulative = np.cumsum(np.asarray(weights)[order], axis=0)
    rank = np.argmax(cumulative >= probability-1e-12, axis=0)
    return sorted_values[rank, np.arange(values.shape[1])]


def solve_dispatch(net_scenarios, weights, price, initial_energy, terminal_energy=6000.0):
    """Solve conditional finite-scenario LP. No realized future enters this API.

    net_scenarios: [scenario, interval], kWh. price: [interval], yuan/kWh.
    Return g,c,d,E for the entire planning horizon and solver evidence.
    """
    started = perf_counter()
    net = np.asarray(net_scenarios, float)
    weights = np.asarray(weights, float)
    price = np.asarray(price, float)
    if net.ndim != 2 or net.shape[1] != len(price):
        raise ValueError("Invalid net scenario/price dimensions")
    s, n = net.shape
    if weights.shape != (s,) or np.any(weights <= 0) or not np.isclose(weights.sum(), 1):
        raise ValueError("Scenario weights must be positive and sum to one")
    if not np.isfinite(net).all() or not np.isfinite(price).all() or np.any(price <= 0):
        raise ValueError("Finite scenarios and strictly positive prices are required")
    if not PARAM.energy_min_kwh <= initial_energy <= PARAM.energy_max_kwh:
        raise ValueError("Initial battery energy out of range")
    # x=[g,c,d,E,q_1,...,q_S]. q_s >= N_s+c-d-g.
    ident = eye(n, format="csr")
    empty = csr_matrix((n, n))
    flow = hstack([-ident, ident, -ident, empty], format="csr")
    inequalities = hstack([kron(np.ones((s, 1)), flow, format="csr"),
                           -eye(s*n, format="csr")], format="csr")
    b_ub = -net.reshape(-1)
    transition = diags([np.ones(n), -np.ones(n-1)], [0, -1], shape=(n, n), format="csr")
    equations = hstack([empty, -PARAM.eta_charge*ident, ident/PARAM.eta_discharge,
                       transition, csr_matrix((n, s*n))], format="csr")
    b_eq = np.zeros(n)
    b_eq[0] = initial_energy
    objective = np.r_[price, np.zeros(3*n),
                      (PARAM.emergency_multiplier*weights[:, None]*price).reshape(-1)]
    limit = PARAM.power_max_kw*PARAM.dt_hours
    bounds = [(0, None)]*n + [(0, limit)]*(2*n)
    bounds += [(PARAM.energy_min_kwh, PARAM.energy_max_kwh)]*n + [(0, None)]*(s*n)
    bounds[4*n-1] = (terminal_energy, terminal_energy)
    result = linprog(objective, A_ub=inequalities, b_ub=b_ub,
                     A_eq=equations, b_eq=b_eq, bounds=bounds, method="highs",
                     options={"primal_feasibility_tolerance": 1e-8,
                              "dual_feasibility_tolerance": 1e-8})
    if not result.success:
        raise RuntimeError(f"Scenario LP failed: {result.message}")
    g, c, d, energy_lp = np.split(result.x[:4*n], 4)
    simultaneous_before = int(((c > 1e-6) & (d > 1e-6)).sum())
    # Exact removal: SOC unchanged, net demand decreases, free disposal allowed.
    efficiency = PARAM.eta_charge*PARAM.eta_discharge
    epsilon = np.minimum(c, d/efficiency)
    c = c-epsilon
    d = d-efficiency*epsilon
    c[np.abs(c) < 1e-9] = 0
    d[np.abs(d) < 1e-9] = 0
    energy = initial_energy + np.cumsum(PARAM.eta_charge*c-d/PARAM.eta_discharge)
    # Independently optimize purchase for the returned battery trajectory.
    quantile = empirical_quantile(net, weights, 1-1/PARAM.emergency_multiplier)
    g = np.maximum(quantile+c-d, 0)
    emergency = np.maximum(net+c-d-g, 0)
    expected_cost = float(price@g + PARAM.emergency_multiplier*(weights[:, None]*emergency*price).sum())
    state_difference = float(np.max(abs(energy-energy_lp)))
    objective_difference = expected_cost-float(result.fun)
    if state_difference > 1e-5 or abs(objective_difference) > 1e-4:
        raise AssertionError(f"LP cleanup changed the optimum: state={state_difference}, cost={objective_difference}")
    if np.any((c > 1e-6) & (d > 1e-6)):
        raise AssertionError("Battery exclusivity cleanup failed")
    if energy.min() < PARAM.energy_min_kwh-1e-6 or energy.max() > PARAM.energy_max_kwh+1e-6:
        raise AssertionError("Battery capacity violation")
    if abs(energy[-1]-terminal_energy) > 1e-6:
        raise AssertionError("Terminal energy violation")
    return {
        "grid": g, "charge": c, "discharge": d, "energy": energy,
        "net_quantile": quantile,
        "log": {"lp_status": int(result.status), "lp_message": result.message,
                "lp_objective_yuan": float(result.fun), "expected_cost_yuan": expected_cost,
                "cleanup_objective_difference_yuan": objective_difference,
                "cleanup_state_max_abs_kwh": state_difference,
                "simultaneous_periods_before_cleanup": simultaneous_before,
                "simultaneous_periods_after_cleanup": 0,
                "horizon_periods": n, "scenario_count": s,
                "planning_initial_kwh": float(initial_energy),
                "planning_terminal_kwh": float(terminal_energy),
                "seconds": perf_counter()-started},
    }


def execute_day(plan, actual_load, actual_pv, price, initial_energy):
    """Execute exactly the first day. Emergency purchase responds only to this slot."""
    n = 144
    g, c, d = (plan[key][:n] for key in ("grid", "charge", "discharge"))
    deficit = actual_load-actual_pv+c-d-g
    emergency = np.maximum(deficit, 0)
    surplus = np.maximum(-deficit, 0)
    energy = initial_energy+np.cumsum(PARAM.eta_charge*c-d/PARAM.eta_discharge)
    expected_energy = plan["energy"][:n]
    if np.max(abs(energy-expected_energy)) > 1e-6:
        raise AssertionError("Execution is inconsistent with the day-ahead battery plan")
    return {"grid_plan_kwh": g, "charge_kwh": c, "discharge_kwh": d,
            "energy_start_kwh": np.r_[initial_energy, energy[:-1]], "energy_end_kwh": energy,
            "emergency_kwh": emergency, "surplus_kwh": surplus,
            "planned_cost_yuan": price*g,
            "emergency_cost_yuan": PARAM.emergency_multiplier*price*emergency,
            "total_cost_yuan": price*g+PARAM.emergency_multiplier*price*emergency}
