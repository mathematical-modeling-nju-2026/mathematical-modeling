# 问题2：两种「90% 效率」口径的全年滚动优化

## 1. 歧义来源

题干（附录 1）只写「充放电效率为 90%」，未指明是**哪一侧**的效率。
两种主流理解会给出**不同的最优调度与不同的费用**：

| | def1_side90（题目主口径：充、放效率各90%） | def2_roundtrip90（将90%解释为往返效率的敏感性口径） |
|---|---|---|
| 表述 | 充电效率 90%、放电效率 90% | **放电量 / 充电量 = 90%** |
| 数学式 | $E_t=E_{t-1}+0.9c_t-d_t/0.9$ | $E_t=E_{t-1}+\eta c_t-d_t/\eta,\ \eta=\sqrt{0.9}$ |
| 参数 | $\eta_c=\eta_d=0.900000$ | $\eta_c=\eta_d=0.948683$ |
| **往返效率** | $0.9\times0.9=\mathbf{0.81}$ | $\eta_c\eta_d=\mathbf{0.90}$ |
| 物理含义 | 充入 1 kWh 电池内只增 0.9；取出 1 kWh 外部只得 0.9 | 充入 1 kWh 最终只能放出 0.9 kWh |

> 采用**对称拆分** $\eta_c=\eta_d=\sqrt{0.9}$，使两侧损耗相同且往返恰为 0.90。

## 2. 实现方式（不修改任何原始代码）

原代码把效率写为**模块级全局常量**，且在函数体内读取，因此可在运行前
**运行期覆盖**，无需复制或改动原文件：

| 文件 | 位置 | 原值 | 覆盖方式 |
|---|---|---|---|
| `common/q2_base/run_1439.py` | 第 46 行 | `ETA_C = ETA_D = 0.90` | 赋新值（LP 在第 145、180 行读取） |

```python
# run_q2_eff.py 的核心逻辑
rolling = load_module(Q2_CODE/"rolling_window.py", "rolling_window")
apply_to_run1439(rolling.base, args.eff)      # ← 覆盖 ETA_C / ETA_D
run_exp = load_module(Q2_CODE/"run_experiment.py", "run_experiment")
run_exp.main()                                 # ← 复用全部原逻辑
```

覆盖率：`ETA_C`/`ETA_D` 覆盖后，LP 递推（145 行）与互斥清理（180 行）
自动使用新效率；预测器与效率无关，故无需重载。

## 3. 目录结构

```
question2/
├── code/                        原模型（未改动，def1 的真身）
├── results/                     ← def1（往返 0.81）的结果，不另存副本
└── efficiency/
    ├── README.md                本说明
    ├── run_log.txt              运行日志
    ├── code/
    │   ├── run_q2_eff.py        主驱动（--eff 选口径）
    │   ├── backfill_q2_eff.py   补校验/发布/指定日期表
    │   ├── rolling_window.py    指纹比对用副本（内容同 question2/code/）
    │   └── run_experiment.py    同上
    └── results/                 ← def2（往返 0.90）的结果
```

**def1 不需要副本**：它与 `question2/results/` 逐值相同
（明细 48,096 行差异 `0.00e+00`），因此 `run_q2_eff.py --eff def1_side90`
直接写回 `question2/results/`。路径统一由 `eta_common.results_dir()` 解析。

`efficiency/results/` 与 `question2/results/` **同构**：`result2.xlsx`、
`daily_summary.csv`、`schedule_detail.csv.gz`、`summary.json`、`comparison.csv`、
`target_table*.csv`、`variants/*`、`sensitivity/valid_residuals/*`。

**原有代码与 `question2/results/` 保持不变。**

## 4. 复现方法

```bash
cd question2/efficiency/code

python -X utf8 run_q2_eff.py --eff def1_side90        # 写回 question2/results/
python -X utf8 run_q2_eff.py --eff def2_roundtrip90   # 写入 efficiency/results/

# 补齐校验 JSON、发布文件与题目指定日期表
python -X utf8 backfill_q2_eff.py --eff def2_roundtrip90
```

四问汇总对照统一用：`python common/efficiency/compare.py`

单次运行约 **7 分钟**（主组 7 个候选 + 有效残差组 3 个候选，各 334 天）。
加 `--skip-extended` 可跳过短窗口扩展组以省时。

驱动脚本在每次运行后自动做**独立校验**（用实际 $\eta_c/\eta_d$ 复算 SOC 递推、
能量平衡、结算、费用），结果写入 `efficiency_verification.json`。

## 5. 结果对照

见 `comparison.txt`。

### 5.1 口径复现性校验（关键）

| 口径 | 主组 56 天等权（元） | 有效残差 56 天等权（元） |
|---|---:|---:|
| **def1_side90** | **14,401,996.98** | **14,389,135.08** |
| 仓库原结果 | 14,401,996.98 | 14,389,135.08 |
| 是否一致 | ✓ 逐值一致 | ✓ 逐值一致 |

def1 与仓库原有结果**完全一致**（明细 48,096 行差异 `0.00e+00`），
证明运行期覆盖机制无副作用。

### 5.2 两口径差异

| 指标 | def1（往返 0.81） | def2（往返 0.90） | 差异 |
|---|---:|---:|---:|
| 有效残差 56 天等权总费用 | 14,389,135.08 | 13,910,066.83 | −479,068.25 (−3.33%) |

> 完整数值见 `common/efficiency/output/comparison.md`。
> 与问题 1 的规律一致：往返效率提高 → 损耗变小 → 费用下降。

## 6. 校验

两口径下均通过全部检查项：

- 逐时段 SOC 递推（用实际 $\eta_c/\eta_d$ 复算，最大残差 ~1e-12）
- 跨时段 SOC 连续性、初末状态（0:00 与年末均为 6000 kWh）
- SOC ∈ [1200, 10800]，充放电 ≤ 833.33 kWh/段
- 同一时段不同时充放电（违反时段数 = 0）
- 逐段能量平衡、紧急购电、结算费用
- 实际净负载与电价取自附件，独立复算总费用

## 7. 与其他问的关系

`common/q2_base/run_1439.py` 被**问题 2 与问题 4-2 共用**。
本目录的覆盖仅在**本进程内生效**，不会影响其他问的运行；
问题 4-2 的同口径结果见 `question4/efficiency/part2/`。
