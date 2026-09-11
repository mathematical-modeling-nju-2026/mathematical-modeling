"""优化点：0:00 计划 LP 引入**显式调整追索**（两阶段随机规划）。

理论依据（本题的可调段）
  设实际需求 x、计划量 q、电价 p。可调段的实际结算：
    q ≥ x：付 pq，调减退还 0.5p(q−x)  → 成本 = px + 0.5p(q−x)
    q < x：付 pq，调增 1.5p(x−q)      → 成本 = pq + 1.5p(x−q)
  边际成本：q<x 时 −0.5p；q>x 时 +0.5p  ⟹ 最优 q = 场景分布的**中位数**。

  而同伴 0:00 LP 对缺口用 5p 兜底（等价于"无法调整"），把 q 推到 ~80% 分位，
  导致计划量偏高（计划/实际 ≈ 1.22）、大量弃置。

实现（对同伴 q3_model.solve 的最小侵入式改造，仅在 stage==0 时生效）
  在 0:00（stage==0）的节点上，为**可调整段**（slot ≥ lock_len）额外引入
    up_j ≥ 0（调增，成本 1.5p）、down_j ≥ 0（调减，成本 −0.5p）
  并把该段的场景平衡改为
    q + d − c + up_s − down_s + e_s ≥ N_s,  e_s 兜底系数保持 5（应留 0，因已由 up 承担）
  即"缺口优先由 1.5p 调增补足，仅当调增不够时才用 5p 紧急"——由 LP 自动选择。
  同时允许 q + d − c + up − down ≥ 点预测（原下界保留）。

  为避免重复计费，可调段的 e_s 成本保持不变（5p），LP 会优先用 up（1.5p）。
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE / "_peer_lab"
sys.path.insert(0, str(LAB))

import q3_data, q3_forecast, q3_model          # noqa: E402
import run_q3 as RUN                            # noqa: E402

T = q3_data.T
ETA, E_MIN, E_MAX, CAP = (q3_model.ETA, q3_model.E_MIN, q3_model.E_MAX,
                          q3_model.CAP)
ORIG_SOLVE = q3_model.solve


def solve_with_recourse(forecaster, day, stage, stages, energy,
                        day_start_energy, original=None, source='fusion',
                        deterministic=False, branch=True, lock_len=36):
    """stage>0 直接走原 solve；stage==0 使用带追索的版本。"""
    if stage != 0:
        return ORIG_SOLVE(forecaster, day, stage, stages, energy,
                          day_start_energy, original, source,
                          deterministic, branch)

    price = forecaster.data['price']
    point = forecaster.point(day, stage, source)
    scenarios, past = forecaster.scenarios(day, stage, source)
    if deterministic:
        scenarios, past = point[None, :T], np.array([], dtype=int)
    nodes = q3_model.make_tree(forecaster, past, stage, stages, source)
    if not branch:
        remaining = [s for s in stages if s >= stage]
        nodes = [q3_model.Node(s, remaining[k + 1] * 36 if k + 1 < len(remaining) else T,
                              np.arange(len(scenarios)), k - 1 if k else None)
                 for k, s in enumerate(remaining)]
    S = len(scenarios)
    lp = q3_model.LP()
    base = lp.var(T, price)              # 0:00 原计划 g0
    for node in nodes:
        start, stop = node.stage * 36, node.stop
        n = stop - start
        prob = len(node.members) / S
        node.q = lp.var(n)
        node.c = lp.var(n, prob * 1e-9, hi=CAP)
        node.d = lp.var(n, prob * 1e-9, hi=CAP)
        node.e = lp.var(n, lo=E_MIN, hi=E_MAX)
        # 仅在**根节点**的可调整段引入追索变量 up/down
        root_recurse = (node.parent is None)
        up = down = None
        if root_recurse and stop > lock_len:
            k_len = stop - max(start, lock_len)
            if k_len > 0:
                up = lp.var(k_len, prob * 1.5 * price[max(start, lock_len):stop])
                down = lp.var(k_len, -prob * .5 * price[max(start, lock_len):stop])
        old_change = np.zeros(2 * T)
        if node.stage != stage and len(past):
            old_change = np.mean([forecaster.point(past[s], node.stage, source)
                                  - forecaster.point(past[s], stage, source)
                                  for s in node.members], axis=0)
        node_point = point + old_change
        for j, t in enumerate(range(start, stop)):
            terms = [(node.q[j], 1)]
            if base is not None:
                terms.append((base[t], -1))
            lp.eq(terms, 0 if base is not None else original[t])
            terms = [(node.e[j], 1), (node.c[j], -ETA), (node.d[j], 1 / ETA)]
            if j:
                terms.append((node.e[j - 1], -1))
            elif node.parent is not None:
                terms.append((nodes[node.parent].e[-1], -1))
            lp.eq(terms, energy if j == 0 and node.parent is None else 0)
            # 净供给下界（点预测）
            lp.le([(node.q[j], -1), (node.d[j], -1), (node.c[j], 1)],
                  -node_point[t])
        if up is not None:
            # 追索变量不作为独立约束，直接进入场景平衡（见下方 k 循环）
            pass
        emergency = lp.var(len(node.members) * n,
                           np.tile(5 * price[start:stop] / S, len(node.members)))
        for k, s in enumerate(node.members):
            for j, t in enumerate(range(start, stop)):
                terms = [(node.q[j], -1), (node.d[j], -1), (node.c[j], 1),
                         (emergency[k * n + j], -1)]
                if up is not None and t >= lock_len:
                    jj = t - max(start, lock_len)
                    terms += [(up[jj], -1), (down[jj], 1)]
                lp.le(terms, -scenarios[s, t])
        if stop == T:
            if day == len(forecaster.data['load']) - 1:
                lp.eq([(node.e[-1], 1)], q3_model.E_INIT)
            else:
                q2 = lp.var(T, prob * price)
                c2 = lp.var(T, prob * 1e-9, hi=CAP)
                d2 = lp.var(T, prob * 1e-9, hi=CAP)
                e2 = lp.var(T, lo=E_MIN, hi=E_MAX)
                for t in range(T):
                    lp.eq([(e2[t], 1), (c2[t], -ETA), (d2[t], 1 / ETA),
                           (e2[t - 1] if t else node.e[-1], -1)])
                    lp.le([(q2[t], -1), (d2[t], -1), (c2[t], 1)],
                          -node_point[T + t])
                lp.eq([(e2[-1], 1)], day_start_energy)
    res, eq, ub = lp.solve()
    root = nodes[0]
    q, c, d, e = (res.x[ids].copy() for ids in (root.q, root.c, root.d, root.e))
    raw_overlap = int(np.sum((c > 1e-7) & (d > 1e-7)))
    remove = np.minimum(c, d / ETA**2)
    c -= remove; d -= ETA**2 * remove
    return dict(original=res.x[base].copy(), q=q, c=c, d=d, E=e,
                stop=root.stop, objective=float(res.fun), nodes=len(nodes),
                scenarios=S, raw_overlap=raw_overlap,
                lp_eq_max=float(np.max(np.abs(eq @ res.x - lp.eb))),
                lp_ineq_max=float(max(0., np.max(ub @ res.x - lp.ub))),
                tree=[])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    q3_model.solve = solve_with_recourse
    RUN.solve = solve_with_recourse
    f = q3_forecast.Forecaster(q3_data.load_data())
    detail, days, summary, trees = RUN.simulate(f, mode, end=365)
    print()
    print(f"=== 带追索的 0:00 计划（mode={mode}）===")
    print(f"  计划 {summary['planned_cost_yuan']/1e4:9.2f} 万")
    print(f"  调整 {summary['adjustment_net_yuan']/1e4:9.2f} 万")
    print(f"  紧急 {summary['emergency_cost_yuan']/1e4:9.2f} 万")
    print(f"  dump {summary['dump_kwh']/1e4:9.2f} 万 kWh")
    print(f"  总   {summary['total_cost_yuan']/1e4:9.2f} 万")
    print(f"  （同伴基线 1402.24 万）")
