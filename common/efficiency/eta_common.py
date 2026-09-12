"""两种「90% 效率」口径的共享定义与校验工具。

本模块**不修改**任何原始代码；所有口径覆盖都在运行期通过给模块全局变量
赋值完成（各问的模型都在函数体内读取这些全局量）。

定义一 def1_side90（储能侧口径，仓库原口径）
    充电效率 90%、放电效率 90%
        E_t = E_{t-1} + 0.9·c_t - d_t/0.9
    ⇒ η_c = η_d = 0.90，往返 η_c·η_d = 0.81

定义二 def2_roundtrip90（GB/T 34131 系国标口径）
    放电量 / 充电量 = 90%
        E_t = E_{t-1} + η·c_t - d_t/η,  η = sqrt(0.9) ≈ 0.948683
    ⇒ η_c = η_d = 0.948683，往返 η_c·η_d = 0.90（对称拆分）

为什么对称拆分在现有代码下「刚好够用」
    问题 3 / 4-3 的模型（q3_model.py）用 `ETA ** 2` 表示往返效率来清理
    同时充放电（`remove = min(c, d/ETA**2)`，`d -= ETA**2 * remove`）。
    对称拆分下 ETA**2 == η_c·η_d == 往返效率，故只需把 ETA 设为 sqrt(0.9)，
    该清理逻辑**自动正确**。问题 2（run_1439.py）显式写了 ETA_C/ETA_D，
    直接分别赋值即可。问题 4-2 的 q42_model.solve_horizon 把往返效率
    硬编码为 .81，需替换该函数（本模块提供参数化版本）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- 口径定义
EFF_DEFS = {
    "def1_side90": dict(
        eta_c=0.9, eta_d=0.9,
        label="定义一：充/放效率各 90%（储能侧口径）",
        roundtrip=0.9 * 0.9,
        note="E_t = E_{t-1} + 0.9·c_t − d_t/0.9；往返 0.81",
    ),
    "def2_roundtrip90": dict(
        eta_c=float(np.sqrt(0.9)), eta_d=float(np.sqrt(0.9)),
        label="定义二：放电量/充电量 = 90%（国标往返口径）",
        roundtrip=0.9,
        note="E_t = E_{t-1} + η·c_t − d_t/η, η=√0.9≈0.948683；往返 0.90",
    ),
}

DEFAULT_KEY = "def1_side90"

# 物理含义：def1 就是仓库原有结果，不另存副本
BASELINE_KEY = "def1_side90"


def get_eff(key):
    """返回 (eta_c, eta_d, roundtrip, label, note)。"""
    if key not in EFF_DEFS:
        raise KeyError(f"未知口径 {key!r}；可选 {list(EFF_DEFS)}")
    d = EFF_DEFS[key]
    return d["eta_c"], d["eta_d"], d["roundtrip"], d["label"], d["note"]


# ------------------------------------------------------- 结果目录解析（去重）
def results_dir(question, key, repo=None):
    """返回某问题在某口径下的结果目录。

    设计要点（消除冗余副本）
        def1_side90 与仓库原有结果逐值一致（已由 verify_def1 验证，
        48096 行明细差异 0.00e+00），因此**不再保存第二份副本**：
            def1_side90  →  questionN/results        （仓库原结果）
            def2_roundtrip90 → questionN/efficiency/results

    这样 `results_dir()` 是所有脚本取路径的唯一入口，重跑、对比、
    出表都无需知道目录名，也就不必再复制一遍原有文件。

    question: 'question1' | 'question2' | 'question3' | 'question4'
              对 question4 可用 'question4/part2'、'question4/part3'
    """
    repo = Path(repo) if repo else Path(__file__).resolve().parents[2]
    q = str(question)

    if q.startswith("question4"):
        # question4 × {part2, part3}
        part = q.split("/")[-1] if "/" in q else "part2"
        if "part3" in q:
            part = "part3"
        if key == "def1_side90":
            return repo / "question4" / part / "results"
        return repo / "question4" / "efficiency" / part / "results"

    if key == "def1_side90":
        return repo / q / "results"
    return repo / q / "efficiency" / "results"


def is_baseline_alias(key):
    """def1 是否等价于仓库原结果（总是 True，供脚本给出提示）。"""
    return key == BASELINE_KEY


def eff_metadata(key):
    eta_c, eta_d, rt, label, note = get_eff(key)
    return dict(efficiency_key=key, efficiency_label=label,
                efficiency_note=note, eta_charge=eta_c, eta_discharge=eta_d,
                eta_roundtrip=rt)


# --------------------------------------------------- 运行期覆盖（不改原码）
def apply_to_run1439(base_module, key):
    """覆盖 common/q2_base/run_1439.py 的 ETA_C / ETA_D。"""
    eta_c, eta_d, _, _, _ = get_eff(key)
    base_module.ETA_C = eta_c
    base_module.ETA_D = eta_d
    return eta_c, eta_d


def apply_to_q3_model(model_module, key):
    """覆盖 q3_model.py 的 ETA（要求对称拆分，见模块 docstring）。"""
    eta_c, eta_d, _, _, _ = get_eff(key)
    if abs(eta_c - eta_d) > 1e-12:
        raise ValueError(
            "q3_model 用 ETA**2 表示往返效率，只支持 η_c == η_d 的对称拆分；"
            f"当前 η_c={eta_c}, η_d={eta_d}")
    model_module.ETA = eta_c
    return eta_c


def make_solve_horizon(eta_c, eta_d, matrices=None):
    """生成参数化的 solve_horizon，替换 q42_model 中硬编码 .81 的版本。

    ⚠️ 关键：原版 q42_model.matrices() 把效率写死在**约束矩阵**里
    （`ev.extend([1., -.9, 1/.9])`），所以只替换投影用的 .81 是不够的
    ——那样 LP 仍按 0.9/0.9 求解，两口径结果会几乎相同（实测仅差 0.001%）。
    因此这里**自建矩阵**，用 η_c / η_d 填递推行，并覆盖投影用的往返效率。

    与原版逐行一致的其余部分：目标、变量布局、上下界、投影与容差。
    """

    def _matrices(K, S):
        """复刻 q42_model.matrices，但递推行用 η_c / η_d（带缓存，每天复用）。"""
        from functools import lru_cache

        @lru_cache(maxsize=64)
        def build(K, S):
            from scipy.sparse import coo_matrix
            n = 4 * K + S * 144
            er, ec, ev = [], [], []
            for k in range(K):
                er.extend([k] * 3)
                ec.extend([3 * K + k, K + k, 2 * K + k])
                ev.extend([1., -eta_c, 1. / eta_d])       # ← 效率在此
                if k:
                    er.append(k)
                    ec.append(3 * K + k - 1)
                    ev.append(-1.)
            er.append(K)
            ec.append(4 * K - 1)
            ev.append(1.)
            aeq = coo_matrix((ev, (er, ec)), shape=(K + 1, n)).tocsr()
            ur, uc, uv = [], [], []
            for k in range(K):
                ur.extend([k] * 3)
                uc.extend([k, K + k, 2 * K + k])
                uv.extend([-1., 1., -1.])
            for s in range(S):
                for t in range(144):
                    row = K + s * 144 + t
                    ur.extend([row] * 4)
                    uc.extend([t, K + t, 2 * K + t, 4 * K + s * 144 + t])
                    uv.extend([-1., 1., -1., -1.])
            aub = coo_matrix((uv, (ur, uc)), shape=(K + S * 144, n)).tocsr()
            bounds = ([(0., None)] * K + [(0., 5000 / 6)] * (2 * K)
                      + [(1200., 10800.)] * K + [(0., None)] * (S * 144))
            return aeq, aub, bounds

        return build(K, S)

    from scipy.optimize import linprog
    eff = eta_c * eta_d

    def solve_horizon(net_plan, net_scenarios, weights, plan_price,
                      scenario_price, initial, terminal):
        K = len(net_plan)
        S = len(weights)
        if K not in (144, 288) or net_scenarios.shape != (S, 144) \
                or scenario_price.shape != (S, 144):
            raise ValueError('Invalid LP dimensions')
        if np.any(plan_price <= 0) or np.any(scenario_price <= 0) \
                or np.any(weights < 0) or not np.isclose(weights.sum(), 1):
            raise ValueError('Positive prices and normalized nonnegative probabilities required')
        objective = np.r_[plan_price, np.zeros(3 * K),
                          (5 * weights[:, None] * scenario_price).ravel()]
        aeq, aub, bounds = _matrices(K, S)
        beq = np.zeros(K + 1)
        beq[0] = initial
        beq[-1] = terminal
        result = linprog(objective, A_ub=aub,
                         b_ub=-np.r_[net_plan, net_scenarios.ravel()],
                         A_eq=aeq, b_eq=beq, bounds=bounds, method='highs')
        if not result.success:
            raise RuntimeError(result.message)
        g, c, d, energy = [result.x[i * K:(i + 1) * K].copy() for i in range(4)]
        raw_overlap = int(((c > 1e-7) & (d > 1e-7)).sum())
        # 与原版相同的 SOC 保持投影，往返效率改为 η_c·η_d
        overlap = np.minimum(c, d / eff)
        c -= overlap
        d -= eff * overlap
        c[np.abs(c) < 1e-9] = 0.
        d[np.abs(d) < 1e-9] = 0.
        z = g + d - c
        emergency = np.maximum(net_scenarios - z[:144], 0.)
        projected_objective = float(
            plan_price @ g + np.sum(5 * weights[:, None] * scenario_price * emergency))
        if abs(projected_objective - result.fun) > 1e-4:
            raise RuntimeError('SOC-preserving projection changed the LP optimum beyond tolerance')
        return dict(g=g, c=c, d=d, E=energy, z=z, objective=projected_objective,
                    raw_overlap=raw_overlap, solver_status=int(result.status))

    return solve_horizon


# ------------------------------------------------------------------ 校验
def verify_matches_baseline(candidate_dir, baseline_dir, cols, tol=1e-6):
    """比较两个结果目录的 CSV 是否逐值一致（用于证明 def1 复现原结果）。"""
    import pandas as pd

    a = pd.read_csv(Path(baseline_dir) / cols["file"])
    b = pd.read_csv(Path(candidate_dir) / cols["file"])
    worst = {}
    for c in cols["columns"]:
        if c in a.columns and c in b.columns:
            worst[c] = float(np.max(np.abs(a[c].to_numpy(float)
                                          - b[c].to_numpy(float))))
    ok = all(v <= tol for v in worst.values())
    return dict(match=ok, max_abs_diff=worst)


def patch_verify_q3(verify_module, eta_c, eta_d):
    """把 verify_q3.check_schedule 换成参数化效率版本。

    run_q3.main() 内部以 `from verify_q3 import check_schedule` 取用该函数，
    并在每次求解后强制校验；原版把 0.9 写死，在 def2 下会误报。
    必须在调用 run_q3.main() 之前完成替换。
    """
    def check_schedule(detail, daily, data, require_year_end=True):
        return check_charge_schedule(detail, daily, data, eta_c, eta_d,
                                     require_year_end=require_year_end)
    verify_module.check_schedule = check_schedule
    return check_schedule


def load_verify_with_eta(path, module_name, eta_c, eta_d):
    """载入 verify_q3.py，但把源码里写死的效率替换为实际 η_c / η_d。

    为什么用「改源码文本」而不是「重写校验函数」
        problem3 与 problem4-3 各有一份 verify_q3.py：二者除效率常数外
        **还有别的差异**（4-3 用 `data['price_rt']` 实时电价结算，Q3 用
        `data['price']`）。若自己重写一份通用校验，容易漏掉这些差异
        （已实际踩过一次坑）。因此这里只对源码做**最小文本替换**：
            `.9*c` / `.9,`  →  `ETA_C*c` …
            `d/.9`          →  `d/ETA_D`
        其余全部逻辑（含 4-3 特有的电价取法）原样保留，避免口径漂移。

    返回 (module, replacement_count)。
    """
    import importlib.util
    import re

    src = Path(path).read_text(encoding="utf-8")
    before = src

    # 1) 递推式校验：after - before - .9*c + d/.9  →  用 ETA_C / ETA_D
    src = src.replace("abs(after-before-.9*c+d/.9)",
                      "abs(after-before-ETA_C*c+d/ETA_D)")
    src = src.replace("np.max(abs(after-before-.9*c+d/.9))",
                      "np.max(abs(after-before-ETA_C*c+d/ETA_D))")
    # 2) 问题2 风格的写法（若存在）
    src = src.replace("ea - eb - 0.9 * c + d / 0.9",
                      "ea - eb - ETA_C * c + d / ETA_D")

    n_sub = 0 if src == before else 1
    if src == before:
        # 兜底：正则匹配任意形式的 `.9*c` 与 `/0.9`
        pat = re.compile(r"abs\(\s*after\s*-\s*before\s*-\s*\.?9\s*\*\s*c\s*\+\s*d\s*/\s*\.?9\s*\)")
        src, k = pat.subn("abs(after-before-ETA_C*c+d/ETA_D)", src)
        n_sub = k

    # 注入 ETA 常量
    src = (f"ETA_C = {eta_c!r}\nETA_D = {eta_d!r}\n"
           f"_EFF_PATCHED = {n_sub > 0}\n") + src

    # 让被载入模块能 import 同目录的 q3_data / q3_forecast / q3_model
    import sys as _sys
    mod_dir = str(Path(path).resolve().parent)
    if mod_dir not in _sys.path:
        _sys.path.insert(0, mod_dir)

    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[module_name] = mod
    exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod, n_sub


def _inject_after_future(src, header):
    """把 header 插到所有 `from __future__` 导入之后（否则会触发 SyntaxError）。"""
    lines = src.splitlines(keepends=True)
    idx = 0
    for i, line in enumerate(lines[:20]):
        s = line.strip()
        if s.startswith("from __future__"):
            idx = i + 1
        elif s and not s.startswith("#") and not s.startswith('"""') and idx:
            break
    return "".join(lines[:idx]) + header + "".join(lines[idx:])


def load_verify_window_with_eta(path, module_name, eta_c, eta_d):
    """载入 question2/code/verify_window.py，把写死的 0.9 效率参数化。

    该文件第 192 行 `ea - eb - 0.9 * c + d / 0.9` 把效率写死；def2 下会误报
    `soc_equation_max_error_kwh`。这里只做**最小文本替换**，其余校验逻辑
    （原始数据比对、工作簿反读、日期元数据等）保持一字不改。

    返回 (module, replacement_count)。
    """
    src = Path(path).read_text(encoding="utf-8")
    old = "residual = _max_abs(ea - eb - 0.9 * c + d / 0.9)"
    new = "residual = _max_abs(ea - eb - ETA_C * c + d / ETA_D)"
    n_sub = src.count(old)
    if n_sub != 1:
        raise RuntimeError(
            f"verify_window.py 的 SOC 校验行未按预期匹配：命中 {n_sub} 次。"
            "原始文件可能已变更，请人工核对。")
    src = src.replace(old, new)
    src = _inject_after_future(src, f"ETA_C = {eta_c!r}\nETA_D = {eta_d!r}\n")
    return _exec_patched(src, path, module_name), n_sub


def load_verify_q42_with_eta(path, module_name, eta_c, eta_d):
    """载入 question4/part2/code/verify_q42.py，把写死的 0.9 效率参数化。

    该文件第 73 行 `near('soc_balance_max_error', ea, eb+.9*c-d/.9)` 把效率写死。
    同样只做最小文本替换。

    返回 (module, replacement_count)。
    """
    src = Path(path).read_text(encoding="utf-8")
    old = "near('soc_balance_max_error', ea, eb+.9*c-d/.9)"
    new = "near('soc_balance_max_error', ea, eb+ETA_C*c-d/ETA_D)"
    n_sub = src.count(old)
    if n_sub != 1:
        raise RuntimeError(
            f"verify_q42.py 的 SOC 校验行未按预期匹配：命中 {n_sub} 次。") from None
    src = src.replace(old, new)
    src = _inject_after_future(src, f"ETA_C = {eta_c!r}\nETA_D = {eta_d!r}\n")
    return _exec_patched(src, path, module_name), n_sub


def _exec_patched(src, path, module_name):
    """按源码文本执行模块，并把它所在目录加入 sys.path（便于 import 同目录依赖）。"""
    import importlib.util
    import sys as _sys

    mod_dir = str(Path(path).resolve().parent)
    if mod_dir not in _sys.path:
        _sys.path.insert(0, mod_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[module_name] = mod
    exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod


def check_charge_schedule(detail, daily, data, eta_c, eta_d,
                          require_year_end=True, T=144):
    """独立校验问题 3 / 4-3 的调度明细（参数化效率版）。

    返回值与 question3/code/verify_q3.py:check_schedule **同构**：
    一个扁平 dict，含全部分项误差与 `pass` 布尔键。
    与原版的唯一差异是把硬编码的 0.9 换成实际使用的 η_c / η_d。
    """
    import pandas as pd

    x = detail
    p = np.tile(data['price'], len(daily))
    g, q, c, d = (x[k].to_numpy() for k in
                  ('original_kwh', 'adjusted_kwh', 'charge_kwh', 'discharge_kwh'))
    day_indices = (pd.to_datetime(x.date) - pd.Timestamp('2025-01-01')).dt.days.to_numpy()
    slots = x.slot.to_numpy(int)
    net = (data['load'][day_indices, slots] - data['pv'][day_indices, slots]) / 6
    emergency = np.maximum(net + c - d - q, 0)
    down = np.maximum(g - q, 0)
    up = np.maximum(q - g, 0)
    # Independently use paid delivered base + breach + new purchases.
    cost = p * np.minimum(g, q) + .5 * p * down + 1.5 * p * up + 5 * p * emergency
    before = x.energy_before_kwh.to_numpy()
    after = x.energy_after_kwh.to_numpy()
    balance = q + d + x.emergency_kwh.to_numpy() - net - c - x.dump_kwh.to_numpy()
    sumcols = ['planned_cost_yuan', 'increase_cost_yuan', 'cancellation_refund_yuan',
               'breach_cost_yuan', 'adjustment_net_yuan', 'emergency_cost_yuan',
               'total_cost_yuan', 'original_kwh', 'adjusted_kwh', 'increase_kwh',
               'decrease_kwh', 'emergency_kwh', 'dump_kwh', 'charge_kwh', 'discharge_kwh']
    summed = x.groupby('date', sort=False)[sumcols].sum().to_numpy()

    errs = dict(
        periods=int(len(x)),
        duplicate_date_slots=int(x.duplicated(['date', 'slot']).sum()),
        energy_min_kwh=float(min(after.min(), before.min())),
        energy_max_kwh=float(max(after.max(), before.max())),
        # 关键：用实际 η_c / η_d 复算递推（原版写死 .9*c + d/.9）
        energy_recursion_max_error=float(np.max(np.abs(after - before - eta_c * c + d / eta_d))),
        chronological_continuity_max_error=float(np.max(np.abs(after[:-1] - before[1:]))),
        initial_energy_kwh=float(before[0]),
        final_energy_kwh=float(after[-1]),
        max_charge_kwh=float(c.max()),
        max_discharge_kwh=float(d.max()),
        min_flow_kwh=float(min(c.min(), d.min(), q.min(), g.min())),
        simultaneous_periods=int(((c > 1e-7) & (d > 1e-7)).sum()),
        energy_balance_max_error=float(abs(balance).max()),
        emergency_max_error=float(np.max(abs(emergency - x.emergency_kwh.to_numpy()))),
        settlement_per_slot_max_error=float(np.max(abs(cost - x.total_cost_yuan.to_numpy()))),
        daily_sum_max_error=float(np.max(abs(summed - daily[sumcols].to_numpy()))),
        cost_recomputed_yuan=float(cost.sum()),
        altered_past_periods=int(np.sum(x.issue_hour.to_numpy() > slots / 6)),
        midnight_block_plan_max_error=float(
            np.max(abs((q - g)[x.issue_hour.to_numpy() == 0]))),
        lp_eq_max=float(daily.lp_eq_max.max()),
        lp_ineq_max=float(daily.lp_ineq_max.max()),
        alternative_no_refund_cost_same_schedule_yuan=float((cost + p * down).sum()))
    errs['eta_charge'] = float(eta_c)
    errs['eta_discharge'] = float(eta_d)
    errs['eta_roundtrip'] = float(eta_c * eta_d)
    errs['pass'] = bool(
        len(x) == len(daily) * T and errs['duplicate_date_slots'] == 0 and
        errs['energy_min_kwh'] >= 1200 - 1e-6 and errs['energy_max_kwh'] <= 10800 + 1e-6 and
        errs['energy_recursion_max_error'] < 1e-6 and
        errs['chronological_continuity_max_error'] < 1e-6 and
        abs(before[0] - 6000) < 1e-6 and
        (not require_year_end or abs(after[-1] - 6000) < 1e-6) and
        max(c.max(), d.max()) <= 5000 / 6 + 1e-6 and errs['min_flow_kwh'] >= -1e-6 and
        errs['simultaneous_periods'] == 0 and errs['energy_balance_max_error'] < 1e-6 and
        errs['emergency_max_error'] < 1e-6 and
        errs['settlement_per_slot_max_error'] < 1e-6 and
        errs['daily_sum_max_error'] < 1e-5 and errs['altered_past_periods'] == 0 and
        errs['midnight_block_plan_max_error'] < 1e-6 and
        errs['lp_eq_max'] < 1e-6 and errs['lp_ineq_max'] < 1e-6)
    return errs


def check_q2_schedule(detail, daily, eta_c, eta_d, tol=1e-6):
    """独立校验问题 2 / 4-2 的逐时段明细。"""
    c = detail['c_kwh'].to_numpy()
    d = detail['d_kwh'].to_numpy()
    g = detail['g_kwh'].to_numpy()
    eb = detail['energy_before_kwh'].to_numpy()
    ea = detail['energy_after_kwh'].to_numpy()
    emerg = detail['emergency_kwh'].to_numpy()
    z = detail['z_kwh'].to_numpy()
    price = detail['price_yuan_per_kwh'].to_numpy()
    actual = detail['actual_net_kwh'].to_numpy()

    errs = dict(
        periods=int(len(detail)),
        energy_recursion_max_error=float(np.max(np.abs(ea - eb - eta_c * c + d / eta_d))),
        continuity_max_error=float(np.max(np.abs(ea[:-1] - eb[1:]))),
        soc_min_kwh=float(min(eb.min(), ea.min())),
        soc_max_kwh=float(max(eb.max(), ea.max())),
        max_charge_kwh=float(c.max()),
        max_discharge_kwh=float(d.max()),
        min_flow_kwh=float(min(g.min(), c.min(), d.min())),
        simultaneous_periods=int(((c > 1e-7) & (d > 1e-7)).sum()),
        emergency_max_error=float(np.max(np.abs(emergency_recompute :=
                                                np.maximum(actual - z, 0) - emerg))),
        cost_max_error=float(np.max(np.abs(price * (g + 5 * emerg)
                                           - detail['total_cost_yuan'].to_numpy()))),
    )
    checks = {
        'energy_recursion_ok': errs['energy_recursion_max_error'] <= tol,
        'continuity_ok': errs['continuity_max_error'] <= tol,
        'soc_bounds_ok': errs['soc_min_kwh'] >= 1200 - tol
                         and errs['soc_max_kwh'] <= 10800 + tol,
        'power_limits_ok': errs['max_charge_kwh'] <= 5000 / 6 + tol
                           and errs['max_discharge_kwh'] <= 5000 / 6 + tol,
        'nonnegative_ok': errs['min_flow_kwh'] >= -tol,
        'no_simultaneous': errs['simultaneous_periods'] == 0,
        'emergency_ok': errs['emergency_max_error'] <= tol,
        'cost_ok': errs['cost_max_error'] <= 1e-4,
    }
    return dict(errors=errs, checks=checks, pass_check=all(checks.values()))
