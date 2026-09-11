"""Scheme B kernels plus causal, online fusion with the released PV forecasts.

Forecast arrays may be precomputed, but decision code only reads today's current
issue and complete historical rows. Actual future values are used for settlement.
"""
import numpy as np
from q3_data import T, HOURS

WINDOW = 56
FIRST_RESIDUAL = 7


def kernel(x, target, known, same_week=False, window=7):
    if same_week:
        ix = [target - 7 * j for j in range(1, 5) if 0 <= target - 7 * j < known]
        return x[ix].mean(0) if ix else None
    hi = min(target, known)
    return x[max(0, hi - window):hi].mean(0) if hi else None


def channel(x, target, known, same_week, drift):
    raw = kernel(x, target, known, same_week)
    if raw is None:
        raw = x[:known].mean(0) if known else np.zeros(T)
    errors = []
    for d in range(max(0, known - drift), known):
        f = kernel(x, d, d, same_week)
        if f is not None:
            errors.append(x[d] - f)
    return raw + np.mean(errors, axis=0) if errors else raw


def history_day(data, d):
    l = np.concatenate([channel(data['load'], j, d, True, 5) for j in (d, d + 1)])
    v = np.concatenate([channel(data['pv'], j, d, False, 28) for j in (d, d + 1)])
    return np.maximum(l, 0), np.maximum(v, 0)


def raw_issue(data, d, stage, history_pv):
    """Linear interpolation of +1..+24 h forecasts. Anchor is observed issue-time PV."""
    start = stage * 36
    flat = data['pv'].ravel()
    anchor = float(flat[d * T + start - 1]) if d * T + start else 0.0
    result = history_pv.copy()
    ends = np.arange(start + 1, start + T + 1)
    result[start:start + T] = np.interp(
        ends, np.arange(25) * 6 + start,
        np.r_[anchor, data['external'][d, stage]])
    return result


class Forecaster:
    def __init__(self, data):
        self.data = data
        n = len(data['load'])
        self.load = np.zeros((n, 2 * T))
        self.hist = np.zeros_like(self.load)
        self.raw = np.zeros((n, 4, 2 * T))
        self.fused = np.zeros_like(self.raw)
        self.alpha = np.ones((n, 4, 4))
        self.bias = np.zeros((n, 4, T))
        flat = data['pv'].ravel()
        for d in range(n):
            self.load[d], self.hist[d] = history_day(data, d)
            for stage in range(4):
                start = stage * 36
                self.raw[d, stage] = raw_issue(data, d, stage, self.hist[d])
                out = self.raw[d, stage].copy()
                # d-1 rows may contain next-day outcomes: train only fully mature rows <= d-2.
                past = np.arange(max(FIRST_RESIDUAL, d - WINDOW), max(FIRST_RESIDUAL, d - 1))
                if len(past) >= 7:
                    y = np.array([flat[r * T + start:r * T + start + T] for r in past])
                    ext = self.raw[past, stage, start:start + T]
                    hist = self.hist[past, start:start + T]
                    for b in range(4):
                        sl = slice(b * 36, (b + 1) * 36)
                        delta = ext[:, sl] - hist[:, sl]
                        den = np.sum(delta * delta)
                        a = np.clip(np.sum(delta * (y[:, sl] - hist[:, sl])) / den, 0, 1) if den > 1e-9 else 1.0
                        self.alpha[d, stage, b] = a
                        old = a * ext[:, sl] + (1 - a) * hist[:, sl]
                        bias = (y[:, sl] - old).mean(0) * len(past) / (len(past) + 14)
                        self.bias[d, stage, sl] = bias
                        dst = slice(start + b * 36, start + (b + 1) * 36)
                        out[dst] = a * self.raw[d, stage, dst] + (1 - a) * self.hist[d, dst] + bias
                self.fused[d, stage] = np.maximum(out, 0)

    def point(self, d, stage, source='fusion'):
        if source == 'history':
            v = self.hist[d]
        elif source == 'external':
            v = self.raw[d, stage]
        else:
            v = self.fused[d, stage]
        return (self.load[d] - v) / 6

    def scenarios(self, d, stage, source='fusion'):
        past = np.arange(max(FIRST_RESIDUAL, d - WINDOW), d)
        if not len(past):
            return self.point(d, stage, source)[None, :T], np.array([], dtype=int)
        residual = np.array([(self.data['load'][r] - self.data['pv'][r]) / 6
                             - self.point(r, stage, source)[:T] for r in past])
        return self.point(d, stage, source)[None, :T] + residual, past

    def price_point(self, d, stage):
        """Causal real-time-price forecast; released prices up to the issue are known."""
        start = stage * 36
        past = self.data['price_rt'][max(0, d - 7):d]
        base = past.mean(0) if len(past) else np.full(T, self.data['price'].mean())
        result = base.copy()
        if start:
            result[:start] = self.data['price_rt'][d, :start]
        return result

    def price_scenarios(self, d, stage):
        point = self.price_point(d, stage)
        past = np.arange(max(FIRST_RESIDUAL, d - WINDOW), d)
        if not len(past):
            return point[None], past
        residual = np.array([self.data['price_rt'][r] - self.price_point(r, stage) for r in past])
        values = np.maximum(point[None] + residual, 1e-5)
        values[:, :stage * 36] = point[:stage * 36]
        return values, past

    def diagnostics(self, start=31, end=365):
        import pandas as pd
        rows = []
        for d in range(start, end):
            for s, hour in enumerate(HOURS):
                sl = slice(s * 36, (s + 1) * 36)
                actual = self.data['pv'][d, sl]
                rows.append(dict(date=self.data['dates'][d], issue_hour=hour,
                                 alpha_next_6h=self.alpha[d, s, 0],
                                 history_mae_kw=np.mean(abs(self.hist[d, sl] - actual)),
                                 external_mae_kw=np.mean(abs(self.raw[d, s, sl] - actual)),
                                 fusion_mae_kw=np.mean(abs(self.fused[d, s, sl] - actual))))
        return pd.DataFrame(rows)
