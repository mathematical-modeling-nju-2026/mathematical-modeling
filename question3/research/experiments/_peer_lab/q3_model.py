"""Finite, nonanticipative scenario-tree LP, solved again at each allowed issue.

Only the root block is executed. Future nodes group historical forecast revisions,
never future realized loads. Stage controls are literally shared variables.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from q3_data import T

ETA = 0.9
E_MIN, E_MAX, E_INIT = 1200., 10800., 6000.
CAP = 5000 / 6

# 实验开关（默认与原版一致）
FLAGS = dict(no_floor=False,    # True: 移除"计划净供给 ≥ 点预测"下界
             floor_ratio=1.0)   # 下界系数（1.0=原点预测；<1 则放松）


@dataclass
class Node:
    stage: int
    stop: int
    members: np.ndarray
    parent: int | None
    q: np.ndarray | None = None
    c: np.ndarray | None = None
    d: np.ndarray | None = None
    e: np.ndarray | None = None


def split_observable(features, members):
    """Deterministic binary k-means on newly observable forecast revisions."""
    if len(members) < 6:
        return [members]
    x = features[members]
    j = int(np.argmax(x.var(0)))
    if x[:, j].std() < 1e-5:
        return [members]
    centers = x[[np.argmin(x[:, j]), np.argmax(x[:, j])]].copy()
    prev = None
    for _ in range(12):
        group = ((x - centers[1]) ** 2).sum(1) < ((x - centers[0]) ** 2).sum(1)
        if min(group.sum(), (~group).sum()) < 3:
            order = np.argsort(x[:, j], kind='stable')
            return [members[order[:len(order)//2]], members[order[len(order)//2:]]]
        if prev is not None and np.array_equal(group, prev):
            break
        centers = np.array([x[~group].mean(0), x[group].mean(0)])
        prev = group
    return [members[~group], members[group]]


def make_tree(forecaster, past, stage, stages, source):
    remaining = [s for s in stages if s >= stage]
    nodes = [Node(stage, (remaining[1] * 36 if len(remaining) > 1 else T),
                  np.arange(max(len(past), 1)), None)]
    parents = [0]
    for k, s in enumerate(remaining[1:], 1):
        stop = remaining[k + 1] * 36 if k + 1 < len(remaining) else T
        previous = remaining[k - 1]
        features = np.array([forecaster.point(r, s, source)[s * 36:]
                             - forecaster.point(r, previous, source)[s * 36:] for r in past])
        children = []
        for parent in parents:
            groups = split_observable(features, nodes[parent].members) if len(past) else [nodes[parent].members]
            for members in groups:
                children.append(len(nodes))
                nodes.append(Node(s, stop, members, parent))
        parents = children
    return nodes


class LP:
    def __init__(self):
        self.cost, self.bounds = [], []
        self.er, self.ec, self.ev, self.eb = [], [], [], []
        self.ur, self.uc, self.uv, self.ub = [], [], [], []

    def var(self, n, cost=0., lo=0., hi=None):
        ids = np.arange(len(self.cost), len(self.cost) + n)
        self.cost.extend(np.broadcast_to(cost, n).tolist())
        self.bounds.extend([(lo, hi)] * n)
        return ids

    def eq(self, terms, rhs=0.):
        row = len(self.eb)
        for col, val in terms:
            self.er.append(row); self.ec.append(int(col)); self.ev.append(val)
        self.eb.append(rhs)

    def le(self, terms, rhs):
        row = len(self.ub)
        for col, val in terms:
            self.ur.append(row); self.uc.append(int(col)); self.uv.append(val)
        self.ub.append(rhs)

    def solve(self):
        n = len(self.cost)
        eq = coo_matrix((self.ev, (self.er, self.ec)), shape=(len(self.eb), n)).tocsr()
        ub = coo_matrix((self.uv, (self.ur, self.uc)), shape=(len(self.ub), n)).tocsr()
        res = linprog(self.cost, A_ub=ub, b_ub=self.ub, A_eq=eq, b_eq=self.eb,
                      bounds=self.bounds, method='highs')
        if not res.success:
            raise RuntimeError(res.message)
        return res, eq, ub


def solve(forecaster, day, stage, stages, energy, day_start_energy,
          original=None, source='fusion', deterministic=False, branch=True,
          tail_emg_mult=5.0, tail_from=36):
    """tail_emg_mult/tail_from：0:00 计划中，非锁定段（≥tail_from）的缺口
    兜底罚系数用 tail_emg_mult（默认 5.0=原版）。降低它体现"后续可调整"。」"""
    price = forecaster.data['price']
    point = forecaster.point(day, stage, source)
    scenarios, past = forecaster.scenarios(day, stage, source)
    if deterministic:
        scenarios, past = point[None, :T], np.array([], dtype=int)
    nodes = make_tree(forecaster, past, stage, stages, source)
    if not branch:
        # Preserve update times but assume no future information gain.
        remaining = [s for s in stages if s >= stage]
        nodes = [Node(s, remaining[k + 1] * 36 if k + 1 < len(remaining) else T,
                      np.arange(len(scenarios)), k - 1 if k else None)
                 for k, s in enumerate(remaining)]
    S = len(scenarios)
    lp = LP()
    base = lp.var(T, price) if original is None else None
    raw_overlap = 0
    for ni, node in enumerate(nodes):
        start, stop = node.stage * 36, node.stop
        n = stop - start
        prob = len(node.members) / S
        node.q = lp.var(n)
        # Tiny throughput tie-breaker only; yuan scale is < 0.1 per year.
        node.c = lp.var(n, prob * 1e-9, hi=CAP)
        node.d = lp.var(n, prob * 1e-9, hi=CAP)
        node.e = lp.var(n, lo=E_MIN, hi=E_MAX)
        if node.stage > 0:
            up = lp.var(n, prob * 1.5 * price[start:stop])
            down = lp.var(n, -prob * .5 * price[start:stop])
        old_change = np.zeros(2 * T)
        if node.stage != stage and len(past):
            old_change = np.mean([forecaster.point(past[s], node.stage, source)
                                  - forecaster.point(past[s], stage, source)
                                  for s in node.members], axis=0)
        node_point = point + old_change
        for j, t in enumerate(range(start, stop)):
            terms = [(node.q[j], 1)]
            if node.stage > 0:
                terms += [(up[j], -1), (down[j], 1)]
            if base is not None:
                terms.append((base[t], -1))
            lp.eq(terms, 0 if base is not None else original[t])
            terms = [(node.e[j], 1), (node.c[j], -ETA), (node.d[j], 1 / ETA)]
            if j:
                terms.append((node.e[j - 1], -1))
            elif node.parent is not None:
                terms.append((nodes[node.parent].e[-1], -1))
            lp.eq(terms, energy if j == 0 and node.parent is None else 0)
            # 计划净供给下界（点预测）；可用 FLAGS 放松或移除
            if not FLAGS['no_floor']:
                lp.le([(node.q[j], -1), (node.d[j], -1), (node.c[j], 1)],
                      -FLAGS['floor_ratio'] * node_point[t])
        emg_cost = 5 * price[start:stop] / S
        if stage == 0 and tail_emg_mult != 5.0:
            # 关键：[36,144) 段可在 6/12/18 点调整，缺口只需 1.5p 调增补足，
            # 故 0:00 计划对该段的兜底罚系数从 5 降到 1.5（体现"可追索"）。
            emg_cost = emg_cost.copy()
            for j, t in enumerate(range(start, stop)):
                if t >= tail_from:
                    emg_cost[j] = tail_emg_mult * price[t] / S
        emergency = lp.var(len(node.members) * n, np.tile(emg_cost, len(node.members)))
        for k, s in enumerate(node.members):
            for j, t in enumerate(range(start, stop)):
                lp.le([(node.q[j], -1), (node.d[j], -1), (node.c[j], 1),
                       (emergency[k * n + j], -1)], -scenarios[s, t])
        if stop == T:
            if day == len(forecaster.data['load']) - 1:
                lp.eq([(node.e[-1], 1)], E_INIT)
            else:
                # Tomorrow is a deterministic value approximation, conditional on the node's forecasts.
                q = lp.var(T, prob * price)
                c = lp.var(T, prob * 1e-9, hi=CAP)
                d = lp.var(T, prob * 1e-9, hi=CAP)
                e = lp.var(T, lo=E_MIN, hi=E_MAX)
                for t in range(T):
                    lp.eq([(e[t], 1), (c[t], -ETA), (d[t], 1 / ETA),
                           (e[t - 1] if t else node.e[-1], -1)])
                    lp.le([(q[t], -1), (d[t], -1), (c[t], 1)], -node_point[T + t])
                lp.eq([(e[-1], 1)], day_start_energy)
    res, eq, ub = lp.solve()
    root = nodes[0]
    q, c, d, e = (res.x[ids].copy() for ids in (root.q, root.c, root.d, root.e))
    raw_overlap = int(np.sum((c > 1e-7) & (d > 1e-7)))
    # This preserves internal SOC and increases useful supply; no disposal upper bound.
    remove = np.minimum(c, d / ETA**2)
    c -= remove; d -= ETA**2 * remove
    return dict(original=res.x[base].copy() if base is not None else original.copy(),
                q=q, c=c, d=d, E=e, stop=root.stop,
                objective=float(res.fun), nodes=len(nodes), scenarios=S,
                raw_overlap=raw_overlap,
                lp_eq_max=float(np.max(np.abs(eq @ res.x - lp.eb))),
                lp_ineq_max=float(max(0., np.max(ub @ res.x - lp.ub))),
                tree=[dict(stage=n.stage, stop=n.stop, parent=n.parent,
                           historical_days=past[n.members].tolist() if len(past) else [],
                           probability=len(n.members) / S) for n in nodes])
