"""Small, auditable extension of scheme B: change only historical scenario weights.

The original forecaster and LP are imported unchanged. The loader is cached in
memory to avoid repeatedly opening attachment 1; no original files are written.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import importlib.util
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / '方案B_1439万' / 'run_1439.py'
spec = importlib.util.spec_from_file_location('scheme_b_original', SOURCE)
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)
base.load_attachment1 = lru_cache(maxsize=1)(base.load_attachment1)


@dataclass(frozen=True)
class Candidate:
    name: str
    window: int = 56
    half_life: float | None = None


# Small family fixed before evaluating the outcomes. Shorter windows are a
# separate extension; the first comparison uses only the first four entries.
CANDIDATES = (
    Candidate('uniform56'), Candidate('half_life7', half_life=7),
    Candidate('half_life14', half_life=14), Candidate('half_life28', half_life=28),
    Candidate('uniform28', window=28), Candidate('uniform42', window=42),
)
BY_NAME = {c.name: c for c in CANDIDATES}
PRIMARY_NAMES = tuple(c.name for c in CANDIDATES[:4])


class Inputs:
    def __init__(self, load=None, pv=None):
        dates, source_load, source_pv = base.load_attachment2()
        self.dates = dates
        self.load = source_load if load is None else load
        self.pv = source_pv if pv is None else pv
        _, self.price, _, _ = base.load_attachment1()
        self.actual = (self.load - self.pv) * base.DT
        self.point = np.array([base.forecast_net(self.load, self.pv, d) * base.DT
                               for d in range(len(self.load))])
        self.tomorrow = np.array([base.forecast_net(self.load, self.pv, d + 1, upto=d) * base.DT
                                  for d in range(len(self.load) - 1)])
        self.residual = self.actual - self.point

    def scenario_data(self, day, candidate, first_residual=0):
        indices = np.arange(max(first_residual, day - candidate.window), day)
        if len(indices) == 0:
            return self.point[day][None, :], np.ones(1), indices
        ages = day - 1 - indices
        weights = np.ones(len(indices)) if candidate.half_life is None else np.exp2(-ages / candidate.half_life)
        weights /= weights.sum()
        return self.point[day][None, :] + self.residual[indices], weights, indices

    def solve_day(self, day, energy, candidate, first_residual=0):
        scenario, weights, indices = self.scenario_data(day, candidate, first_residual)
        prediction = self.point[day] if day == 364 else np.r_[self.point[day], self.tomorrow[day]]
        terminal = 6000. if day == 364 else energy
        plan = base.solve_horizon(prediction, scenario, weights,
                                  np.tile(self.price, len(prediction)//144), energy, terminal)
        return plan, weights, indices


def weighted_quantile(values, weights, tau=.8):
    """Left empirical quantile in every column; same scenario weight per day."""
    order = np.argsort(values, axis=0, kind='stable')
    sorted_values = np.take_along_axis(values, order, axis=0)
    cumulative = np.cumsum(weights[order], axis=0)
    positions = np.argmax(cumulative >= tau - 1e-12, axis=0)
    return sorted_values[positions, np.arange(values.shape[1])]


def prequential_scores(inputs, names=PRIMARY_NAMES, first_residual=0):
    """Score forecasts made using only days < d, never refit old predictions."""
    scores = np.full((365, len(names)), np.nan)
    quantiles = np.full((365, len(names), 144), np.nan)
    for day in range(max(7, first_residual + 1), 365):
        for k, name in enumerate(names):
            scenarios, weights, _ = inputs.scenario_data(day, BY_NAME[name], first_residual)
            target = np.maximum(inputs.point[day], weighted_quantile(scenarios, weights))
            error = inputs.actual[day] - target
            quantiles[day, k] = target
            # Includes the point-forecast floor but does not substitute for the SOC-coupled LP.
            scores[day, k] = float(inputs.price @ np.where(error >= 0, .8*error, -.2*error))
    return scores, quantiles


def choose_week(day, scores, names=PRIMARY_NAMES, lookback=28, update_every=7):
    """Every 7 days choose on the previous 28 completed days. Tie order is fixed."""
    decision_day = 31 + ((day - 31)//update_every)*update_every
    lo = max(7, decision_day - lookback)
    historic = scores[lo:decision_day]
    valid = np.isfinite(historic).all(axis=1)
    if valid.sum() < 14:
        return names[0], decision_day - 1, [None]*len(names)
    means = historic[valid].mean(axis=0)
    return names[int(np.argmin(means))], decision_day - 1, means.tolist()
