# 效率口径说明（问题 3）

## 现状

鉴于问题 1 已完成两种「90% 效率」口径的对照实现并给出定量差异
（见 `question1/efficiency/`），本目录为问题 3 预留分类骨架，**当前尚未实现**。

## 两种口径（与问题 1 一致）

| | 定义一（储能侧口径） | 定义二（国标往返口径） |
|---|---|---|
| 递推式 | $E_t=E_{t-1}+0.9c_t-d_t/0.9$ | $E_t=E_{t-1}+\eta c_t-d_t/\eta$，$\eta=\sqrt{0.9}$ |
| 单向效率 | $\eta_c=\eta_d=0.9$ | $\eta_c=\eta_d=0.948683$ |
| 往返效率 | **0.81** | **0.90** |
| 对应结果 | 现有 `results/`（原口径，1402.24 万元） | 待生成 |

## 待改造的具体位置

问题 3 的代码位于 `question3/code/`，效率参数集中在 `q3_model.py`：

| 行号 | 现有实现 | 改造要点 |
|---|---|---|
| 12 | `ETA = 0.9` | 拆为 `ETA_C` / `ETA_D` |
| 149 | `terms = [(node.e[j], 1), (node.c[j], -ETA), (node.d[j], 1 / ETA)]` | 充电项用 `-ETA_C`，放电项用 `1/ETA_D` |
| 171 | `lp.eq([(e[t], 1), (c[t], -ETA), (d[t], 1 / ETA), ...])` | 同上 |
| 180–181 | `remove = np.minimum(c, d / ETA**2)`；`c -= remove; d -= ETA**2 * remove` | **同时充放电清理逻辑**，需改为 `ETA_C*ETA_D` |

> 第 180–181 行的互斥清理用到了 `ETA**2`（即往返效率的倒数关系）。
> 在两个单向效率对称时 `ETA**2 = ETA_C*ETA_D`，但显式改写更安全：
> 应以 `np.minimum(c, d / (ETA_C * ETA_D))` 与 `d -= (ETA_C * ETA_D) * remove` 表达。

## 校验脚本需同步

`question3/code/verify_q3.py` 中若含效率硬编码（检查 `0.9` / `ETA`），
须改为读取当前口径的参数，否则校验会误报。

## 建议的落地方式

```
question3/efficiency/
├── def1_side90/results/         定义一（往返 0.81）＝ 现有结果
└── def2_roundtrip90/results/    定义二（往返 0.90）
```

运行方式与问题 1 对齐（命令行参数选择口径），
结果写入对应子目录，**不覆盖现有 `results/`**。

> 提示：问题 3 单次运行约 2 分钟（`--mode all`，334 天）。
> 若只需主方案，可用 `--mode all` 而非 `suite` 以节省时间。

## 参考

问题 1 的完整实现与对照结论见 `question1/efficiency/README.md`。
