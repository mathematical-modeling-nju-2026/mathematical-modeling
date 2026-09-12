# 问题4：两种「90% 效率」口径的结果对照

问题 4 要求「在波动电价下重新计算问题 2 和问题 3」，因此本目录分两部分：

- `part2/` —— 对应问题 2（波动电价下的日前计划）
- `part3/` —— 对应问题 3（波动电价 + 多时点调整）

## 1. 口径定义

| | `def1_side90`（储能侧口径，仓库原口径） | `def2_roundtrip90`（GB/T 34131 系国标口径） |
|---|---|---|
| 含义 | 充电效率 90%、放电效率 90% | **放电量 / 充电量 = 90%** |
| 参数 | $\eta_c=\eta_d=0.900000$ | $\eta_c=\eta_d=0.948683$ |
| **往返效率** | $0.9\times0.9=\mathbf{0.81}$ | $\eta_c\eta_d=\mathbf{0.90}$ |

> **def1 与仓库原有结果逐值相同**（明细 48,096 行差异 `0.00e+00`），
> 因此**不另存副本**：
> - 4-2 的 def1 = `question4/part2/results/`
> - 4-3 的 def1 = `question4/part3/results/`

## 2. 目录结构

```
question4/
├── part2/                        4-2 原模型（def1 真身）
│   ├── code/  results/
├── part3/                        4-3 原模型（def1 真身）
│   ├── code/  results/
└── efficiency/
    ├── README.md                 本说明
    ├── part2_run_log.txt / part3_run_log.txt
    ├── code/
    │   ├── run_q42_eff.py        4-2 主驱动
    │   ├── run_q43_eff.py        4-3 主驱动
    │   ├── backfill_q42_eff.py   4-2 补校验/发布/指定日期表
    │   └── backfill_figures.py   补 Q1/Q3/4-3 的图
    ├── part2/results/            ← 4-2 的 def2 结果
    └── part3/results/            ← 4-3 的 def2 结果
```

路径统一由 `eta_common.results_dir("question4/part2", key)` 解析。

## 3. 实现方式（不修改任何原始文件）

### 3.1 4-2 的两处关键覆盖

```python
q42 = load_module(P2_CODE / "q42_model.py", "q42_model")
q42.solve_horizon = make_solve_horizon(eta_c, eta_d)   # ① 含约束矩阵
q42.HERE, q42.BASE_DIR = out, q2_dir                    # ② 输出与 Q2 基线指向本口径
```

**① 为什么必须整体替换 `solve_horizon`**（本项目最大的坑）：
`q42_model.matrices()` 把效率**写死在 LP 约束矩阵**里
（`ev.extend([1., -.9, 1/.9])`）。只替换目标里投影用的 `.81` 是无效的——
LP 仍按 0.9/0.9 求解，两口径结果只会差 0.001%（实测 85 元）。
`make_solve_horizon()` 因此**自建矩阵**，用 η_c/η_d 填递推行。

**② `BASE_DIR` 指向同口径的 Q2 结果**，保证「Q2 重结算基线」与主模型
用同一套效率，避免混口径比较。

另需覆盖 `run_1439.ETA_C/ETA_D`（1 月预热用），否则
`check_information` 的「固定电价退化为 Q2」解析例会按 0.9/0.9 判分而误报失败。

### 3.2 4-3 的覆盖

与问题 3 相同的 `q3_model.ETA` 覆盖，外加**必须在导入 `q3_data` 之前**
设置 `CUMCM_C_ATTACHMENT_DIR`（`attachment_dir()` 按 `parents[2]` 推断，
在 `efficiency/` 深度下会失效）。

## 4. 复现方法

```powershell
cd question4/efficiency/code

# 4-2
python -X utf8 run_q42_eff.py --eff def2_roundtrip90
python -X utf8 backfill_q42_eff.py --eff def2_roundtrip90

# 4-3
python -X utf8 run_q43_eff.py --eff def2_roundtrip90 --mode suite

# 补图（Q1 / Q3 / 4-3）
python -X utf8 backfill_figures.py --all
```

`run_q42_eff.py` 要求**同口径的 Q2 结果已存在**，会据此做输入校验。

四问汇总统一用：`python common/efficiency/compare.py`

## 5. 结果对照

### 5.1 问题 4-2（波动电价下的问题 2）

| 方案 | def1（往返 0.81） | def2（往返 0.90） |
|---|---:|---:|
| 原 Q2 计划按附件 4 重结算 | 15,184,704.23 | 14,692,410.07 |
| 平均电价模型 | 15,160,921.45 | 14,682,432.08 |
| **联合场景模型（主方案）** | **15,163,043.89** | **14,684,028.55** |
| 当日电价已知（对照） | 15,033,043.18 | 14,511,385.13 |

**主方案总费用下降 479,015.34 元（−3.16%）。**

诚实说明：两口径下「平均电价」在本年度回测中都略优于「联合场景」
（def1 差 2,122 元，def2 差 1,596 元）。我们仍以联合场景为主方案，
因为它保留了正确的概率结构；单一年度的千元级差异不具统计显著性。

### 5.2 问题 4-3（波动电价 + 多时点调整）

| 更新频率方案 | def1（往返 0.81） | def2（往返 0.90） |
|---|---:|---:|
| B_aligned（无融合，仅 0 点） | 15,516,984.54 | 15,021,344.08 |
| only_0（融合预报，仅 0 点） | 15,295,120.10 | 14,802,466.80 |
| at_0_6 | 15,173,094.46 | 14,689,131.22 |
| at_0_6_12 | 15,068,610.47 | 14,587,543.54 |
| **all（主方案）** | **15,061,735.43** | **14,579,714.65** |

**主方案总费用下降 482,020.78 元（−3.20%）。**

「多时点调整」的收益（B_aligned → 主方案）：def1 **45.52 万元**，
def2 **44.16 万元**。两口径下都显示：波动电价放大了调整机制的价值
（对比问题 3 的 36.75 万元），因为多时点更新不仅能修正光伏预报，
还能修正**电价预期**。

## 6. 校验

### 4-2
- `verification.json`：独立解析 Excel 与明细，复算 SOC/物理约束/账目
  - 明确**不 import 任何优化器**，是真正的独立校验
  - 含**篡改检测**：人工改动电价/储电量/紧急电量后必须被拒
- `information_verification.json`：未来信息隔离测试
  - 扰动未来价格/负载/光伏 → 当前决策变化必须为 0
  - 「当日电价已知」方案也不得读取次日实际价格
- `publication_verification.json`：发布文件与已验证变体**逐字节相同**
- `efficiency_verification.json`：用实际 η_c/η_d 复算

### 4-3
- `verification.json`：pass = **True**，含信息边界检查

两口径下均通过全部检查项。

## 7. 交付文件

| 问题 | 结果文件 | 题目指定日期表 |
|---|---|---|
| 4-2 | `part2/results/result4-2.xlsx` | `part2/results/target_days/table{1,2,3}_*.csv` |
| 4-3 | `part3/results/result4-3.xlsx` | `part3/results/target_table{1,2,3}.csv` |

> 注：`part3/results/result3.xlsx` 是历史遗留文件。4-3 的
> `verify_q3.py` 实际校验的是 `result4-3.xlsx`，与本对照无关。

四问的表1/表2/表3 汇总版（含「全天购电费」与「0:00/24:00 储电量」）
见 `common/efficiency/output/指定日期结果_*.xlsx`。
