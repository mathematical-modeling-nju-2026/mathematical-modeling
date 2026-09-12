# 问题3：两种「90% 效率」口径的结果对照

## 1. 口径定义

题目附录 1 只写「储能设备的充放电效率为 90%」，存在两种合理解读：

| | `def1_side90`（储能侧口径，仓库原口径） | `def2_roundtrip90`（GB/T 34131 系国标口径） |
|---|---|---|
| 含义 | 充电效率 90%、放电效率 90% | **放电量 / 充电量 = 90%** |
| 参数 | $\eta_c=\eta_d=0.900000$ | $\eta_c=\eta_d=0.948683$ |
| **往返效率** | $0.9\times0.9=\mathbf{0.81}$ | $\eta_c\eta_d=\mathbf{0.90}$ |

`def2` 采用**对称拆分** $\eta=\sqrt{0.9}$。之所以能直接复用现有代码：
`q3_model.py` 用 `ETA ** 2` 表示往返效率来清理同时充放电，
对称拆分下 `ETA**2 == η_c·η_d == 往返效率`，该逻辑自动正确，
因此只需覆盖 `ETA` 一个量。

> **def1 与仓库原有结果逐值相同**（明细 48,096 行差异 `0.00e+00`），
> 因此**不另存副本**——def1 的结果目录就是 `question3/results/` 本身。

## 2. 目录结构

```
question3/
├── code/                        原模型（未改动，def1 的真身）
├── research/                    探索性实验（与本对照无关）
├── results/                     ← def1（往返 0.81）的结果
└── efficiency/
    ├── README.md                本说明
    ├── run_log.txt              运行日志
    ├── code/
    │   └── run_q3_eff.py        主驱动（--eff 选口径）
    └── results/                 ← def2（往返 0.90）的结果
        ├── result3.xlsx         交付表（计划购电量/调整购电量/充放电量/紧急购电量）
        ├── schedule_detail.csv  48,096 行逐段明细
        ├── comparison.csv       五个更新频率方案对照
        ├── target_table{1,2,3}.csv  题目指定日期表
        ├── target_daily.csv     指定日期日汇总
        ├── verification.json    独立校验
        ├── efficiency_summary.json / efficiency_verification.json
        ├── figures/             成本对照、预测融合、指定日期调度
        └── comparisons/         各更新频率的对照运行
```

路径统一由 `eta_common.results_dir()` 解析，脚本不硬编码目录名。

## 3. 实现方式（不修改任何原始文件）

原代码把效率写为**模块级全局常量** `q3_model.ETA`，且在函数体内读取，
因此可在运行期覆盖：

```python
q3_model = load_module(Q3_CODE / "q3_model.py", "q3_model")
apply_to_q3_model(q3_model, args.eff)      # ← 覆盖 ETA（要求对称拆分）
```

另需把 `verify_q3.check_schedule` 换成参数化效率版本（原版把 0.9 写死）：

```python
q3_model.check_schedule = patch_verify_q3(verify_q3, eta_c, eta_d)
```

`question4/efficiency/code/run_q43_eff.py` 另需在**导入 `q3_data` 之前**
设置环境变量 `CUMCM_C_ATTACHMENT_DIR`，因为 `q3_data.attachment_dir()`
按 `parents[2]` 推断路径，在 `efficiency/` 深度下会失效。

## 4. 复现方法

```powershell
cd question3/efficiency/code

# def1：写回 question3/results/（应复现 14,022,396.98 元）
python -X utf8 run_q3_eff.py --eff def1_side90 --mode suite

# def2：写入 efficiency/results/
python -X utf8 run_q3_eff.py --eff def2_roundtrip90 --mode suite
```

`--mode suite` 跑五个更新频率方案（B_aligned / only_0 / at_0_6 /
at_0_6_12 / all），约 5 分钟。

四问汇总统一用：`python common/efficiency/compare.py`

## 5. 结果对照

### 5.1 全年总费用（元，334 天）

| 更新频率方案 | def1（往返 0.81） | def2（往返 0.90） |
|---|---:|---:|
| B_aligned（无融合，仅 0 点） | 14,389,892.50 | 13,910,630.69 |
| only_0（融合预报，仅 0 点） | 14,181,445.03 | 13,709,320.63 |
| at_0_6 | 14,101,371.47 | 13,634,446.05 |
| at_0_6_12 | 14,022,358.10 | 13,557,942.80 |
| **all（主方案，0/6/12/18 点）** | **14,022,396.98** | **13,558,297.17** |

**主方案总费用下降 464,099.81 元（−3.31%）。**

### 5.2 调整机制的价值

固定电价下「多时点调整」的收益（B_aligned → 主方案）：
- def1：36.75 万元
- def2：35.23 万元

## 6. 校验

`results/verification.json` 记录独立校验结果，pass = **True**。
校验内容（由 `verify_q3.check_schedule` 执行，已参数化效率）：

- 逐段 SOC 递推（用实际 $\eta_c/\eta_d$ 复算）
- 跨时段 SOC 连续性、日内首末状态、年末回到 6000 kWh
- SOC ∈ [1200, 10800] kWh
- 同一时段不同时充放电
- 逐段能量平衡、紧急购电、弃置电量
- 分项结算：原计划费、增购费（1.5 倍）、退款、违约费（50%）、紧急费（5 倍）
- 实际净负载与电价取自附件独立复算

## 7. 与其他问的关系

`question3/code/` 与 `question4/part3/code/` 是两份**独立**的 q3 实现，
差异在于电价口径：Q3 用固定电价 `data['price']`，4-3 用实时电价
`data['price_rt']`。因此两者的 `verify_q3.py` 也不通用——
`eta_common.load_verify_with_eta()` 采用**最小源码文本替换**而非重写，
以保留各自特有的结算逻辑（此处曾踩过坑）。

问题 4-3 的同口径结果见 `question4/efficiency/part3/`。
