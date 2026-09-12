# 「90% 效率」两种口径：说明与复现

本文件是效率口径研究的唯一总入口。原根目录下的
`efficiency_comparison.md`、`efficiency_comparison.json`、
`efficiency_summary_for_user.txt`、`efficiency_def1_reproduction.txt`
已全部由 `common/efficiency/compare.py` 取代并删除。

---

## 1. 为什么要做这个对照

题目附录 1 只写「储能设备的充放电效率为 90%」，存在两种合理解读：

| | `def1_side90`（储能侧口径，仓库原口径） | `def2_roundtrip90`（GB/T 34131 系国标口径） |
|---|---|---|
| 含义 | 充电效率 90%、放电效率 90% | 放电量 / 充电量 = 90% |
| 递推式 | $E_t=E_{t-1}+0.9c_t-\dfrac{d_t}{0.9}$ | $E_t=E_{t-1}+\eta c_t-\dfrac{d_t}{\eta},\ \eta=\sqrt{0.9}$ |
| 参数 | $\eta_c=\eta_d=0.90$ | $\eta_c=\eta_d=0.948683$ |
| **往返效率** | **0.81** | **0.90** |

`def2` 采用对称拆分 $\eta=\sqrt{0.9}$，使往返效率恰为 0.90。之所以能直接套用
现有代码：问题 3 / 4-3 的模型用 `ETA**2` 表示往返效率来清理同时充放电，
对称拆分下 `ETA**2 == η_c·η_d == 往返效率`，该逻辑自动正确。

> **重要**：`def1_side90` 与仓库原有结果**逐值完全相同**（实测明细 48,096 行
> 差异 `0.00e+00`，Q1 的 160 个数值单元格差异 `0.00e+00`）。因此**不再保存
> 第二份副本**——`def1` 的「结果目录」就是 `questionN/results/` 本身。

---

## 2. 目录结构

```
questionN/
├── code/                     原模型（未改动，def1 的真身）
├── results/                  ← def1_side90 的结果（就是这里，无副本）
└── efficiency/
    ├── code/                 参数化效率的驱动脚本
    ├── results/              ← def2_roundtrip90 的结果
    └── README.md

common/
├── q2_base/                  第二问基础预测/LP/读取层
├── plotting/                 样式与导出
└── efficiency/
    ├── eta_common.py         两口径定义 + 校验工具 + 统一路径解析
    ├── compare.py            唯一汇总入口（对照表 + def1 校验 + 指定日期表）
    └── output/               compare.py 的产物
```

第四问按 `question4/efficiency/{part2,part3}/results/` 组织。

**路径解析统一由 `eta_common.results_dir()` 负责**，脚本不再硬编码目录名：

```python
results_dir("question2", "def1_side90")       # → question2/results
results_dir("question2", "def2_roundtrip90")  # → question2/efficiency/results
results_dir("question4/part2", "def2_roundtrip90")
                                              # → question4/efficiency/part2/results
```

---

## 3. 复现命令

```powershell
cd question1/efficiency/code
python -X utf8 run_q1_eff.py --eff def2_roundtrip90

cd question2/efficiency/code
python -X utf8 run_q2_eff.py --eff def2_roundtrip90
python -X utf8 backfill_q2_eff.py --eff def2_roundtrip90   # 补校验/发布/指定日期表

cd question3/efficiency/code
python -X utf8 run_q3_eff.py --eff def2_roundtrip90 --mode suite

cd question4/efficiency/code
python -X utf8 run_q42_eff.py --eff def2_roundtrip90
python -X utf8 backfill_q42_eff.py --eff def2_roundtrip90
python -X utf8 run_q43_eff.py --eff def2_roundtrip90 --mode suite
python -X utf8 backfill_figures.py --all                   # 补 Q1/Q3/Q4-3 图

cd common/efficiency
python -X utf8 compare.py                                  # 汇总一切
```

`--eff` 省略时默认 `def1_side90`，此时直接写 `questionN/results/`（即原结果）。

---

## 4. 结果对照

`python common/efficiency/compare.py` 输出到 `common/efficiency/output/`：

| 文件 | 内容 |
|---|---|
| `comparison.md` / `.csv` / `.json` | 四问两口径总费用对照 |
| `def1_equivalence.json` | def1 与仓库原结果的一致性核验 |
| `指定日期结果_def1_side90.xlsx` / `.md` | 四问的题目表1/表2/表3 |
| `指定日期结果_def2_roundtrip90.xlsx` / `.md` | 同上 |

### 总电费（元）

| 问题 | 定义一（往返 0.81） | 定义二（往返 0.90） | 差额 | 变化率 |
|---|---:|---:|---:|---:|
| 问题一 | 35,126.95 | 33,801.50 | −1,325.45 | −3.77% |
| 问题二 | 14,389,135.08 | 13,910,066.83 | −479,068.25 | −3.33% |
| 问题三 | 14,022,396.98 | 13,558,297.17 | −464,099.81 | −3.31% |
| 问题四-2 | 15,163,043.89 | 14,684,028.55 | −479,015.34 | −3.16% |
| 问题四-3 | 15,061,735.43 | 14,579,714.65 | −482,020.78 | −3.20% |

**四点结论**

1. 往返效率由 0.81 提高到 0.90（+11.1%），总费用下降 **3.16%–3.77%**。
2. 四个问题的降幅高度一致，说明这是效率口径本身的影响，而非模型不稳定。
3. 收益来源是套利空间变大：往返损失减少，充放电循环更划算。
4. 两口径下**调度策略本身也会变化**（不是对同一计划重新计价），
   所以费用差异是真实的模型输出差异。

---

## 5. 工程要点（改代码时务必注意）

1. **效率常数写在约束矩阵里。** `q42_model.matrices()` 把 `[1., -.9, 1/.9]`
   编进 LP 约束，只替换投影用的 `.81` 会让两口径结果几乎相同（实测仅差 0.001%）。
   必须用 `eta_common.make_solve_horizon(eta_c, eta_d)` 自建矩阵。
2. **校验器也硬编码了 0.9。** `verify_window.py` 与 `verify_q42.py` 各有一处；
   用 `load_verify_window_with_eta` / `load_verify_q42_with_eta` 做最小源码
   文本替换。注入常量须放在 `from __future__` 之后，否则 SyntaxError。
3. **Q4-2 的 `check_information`** 用 `run_1439` 复算「固定电价退化为 Q2」的
   解析例，不覆盖其 `ETA_C/ETA_D` 会误报失败。
4. **Q4-3 的 `verify_q3.py` 校验的是 `result4-3.xlsx`**，不是 `result3.xlsx`；
   后者是历史遗留文件，与本对照无关。
5. **零改动保证**：原 `question{1..4}/code`、`common/q2_base` 与各问
   `results/` 中的算法代码从未被修改；所有口径覆盖都在运行期通过给模块全局量
   赋值完成。
