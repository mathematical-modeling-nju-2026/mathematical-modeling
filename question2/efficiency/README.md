# 效率口径说明（问题 2–4）

## 现状

用户要求先在**问题 1** 落地两种「90% 效率」口径的对照实现
（见 `question1/efficiency/`），本目录为问题 2–4 预留的分类骨架，
**当前尚未实现**，因为：

1. 问题 1 已给出两口径的定量差异（全天购电费相差 1,325.45 元，3.77%）；
2. 问题 2–4 是全年 334 天滚动优化，单次运行 2–5 分钟，
   两口径 × 4 条流水线需额外约 30–40 分钟计算；
3. 需先确认问题 1 的对照结论是否被接受，再决定是否推广。

## 两种口径（与问题 1 一致）

设 $E_t$ 为第 $t$ 段末储电量，$c_t$ 为充电量、$d_t$ 为放电量（均指设备外端）：

| | 定义一（储能侧口径） | 定义二（国标往返口径） |
|---|---|---|
| 递推式 | $E_t=E_{t-1}+0.9c_t-d_t/0.9$ | $E_t=E_{t-1}+\eta c_t-d_t/\eta$，$\eta=\sqrt{0.9}$ |
| 单向效率 | $\eta_c=\eta_d=0.9$ | $\eta_c=\eta_d=0.948683$ |
| 往返效率 | **0.81** | **0.90** |
| 对应仓库结果 | 现有 `results/`（原口径） | 待生成 |

## 待改造的代码位置

各问的效率参数分散在以下文件，改造时需统一：

| 流水线 | 文件 | 位置 | 现有实现 |
|---|---|---|---|
| 问题2 | `common/q2_base/run_1439.py` | 第 46 行 | `ETA_C = ETA_D = 0.90` |
| 问题2 | `common/q2_base/run_1439.py` | 第 145、180 行 | 递推与效率耦合 |
| 问题2 | `question2/code/verify_window.py` | 第 192 行 | 校验用 `0.9 * c + d / 0.9` |
| 问题3 | `question3/code/q3_model.py` | 第 12 行 | `ETA = 0.9` |
| 问题3 | `question3/code/q3_model.py` | 第 149、171、180–181 行 | 递推、互斥清理 |
| 问题4-2 | `question4/part2/code/q42_model.py` | 复用 Q2 公共模型 | — |
| 问题4-3 | `question4/part3/code/q3_model.py` | 第 12 行 | `ETA = 0.9` |

> 注意：`common/q2_base/run_1439.py` 中已有 `ETA_C` / `ETA_D` 两个变量
> （当前都取 0.90），改为定义二只需把两者同时置为 $\sqrt{0.9}$，
> 但**互斥清理逻辑**（`q3_model.py:180-181`）中含 `ETA**2`，需一并核对。

## 建议的落地方式

沿用问题 1 的模式：

```
question2/efficiency/{def1_side90,def2_roundtrip90}/results/
question3/efficiency/{def1_side90,def2_roundtrip90}/results/
question4/efficiency/{def1_side90,def2_roundtrip90}/{part2,part3}/results/
```

每条流水线通过环境变量或命令行参数选择口径，结果写入对应子目录，
**不覆盖现有 `results/`**。

## 参考

问题 1 的完整实现与对照结论见 `question1/efficiency/README.md`。
