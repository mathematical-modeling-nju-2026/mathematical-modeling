# 第三问

采用“在线预报融合 + 经验场景树LP + 跨日滚动执行”，继承方案B的负载与历史光伏预测内核。原题来自 `../raw`，本目录不修改其他问的实现。

## 运行

从 `E:\math_model` 执行（已建立项目虚拟环境）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r mathematical-modeling/C_yang/ques3/requirements.txt
.\.venv\Scripts\python.exe -X utf8 mathematical-modeling/C_yang/ques3/run_q3.py
.\.venv\Scripts\python.exe -X utf8 mathematical-modeling/C_yang/ques3/verify_q3.py
.\.venv\Scripts\python.exe -X utf8 mathematical-modeling/C_yang/ques3/plot_q3.py
```

`run_q3.py` 默认计算五个全年对照；`--mode all` 只计算四次更新主方案。`--days 3 --out smoke` 可快速检查前三天，不把短期样例视为全年结果。所有初末状态、时间和结算假设见 [建模说明.md](建模说明.md)。

## 文件

| 文件 | 用途 |
|---|---|
| `q3_data.py` | 读取原始附件，校验形状、非负性，记录数据SHA256 |
| `q3_forecast.py` | 因果历史预测、逐发布时刻融合、整日残差场景 |
| `q3_model.py` | 信息分支、共享节点变量、购电与储能LP |
| `run_q3.py` | 全年滚动、费用结算、Excel与CSV导出、对照实验 |
| `verify_q3.py` | 独立能量及费用复算、未来扰动、Excel反读 |
| `plot_q3.py` | 从已保存CSV绘制PNG和PDF |
| `result3.xlsx` | 题目要求的四张表；调整购电量为最终总量 |
| `schedule_detail.csv` | 每十分钟的原计划、最终计划、增减量、储能与各费用 |
| `daily_summary.csv` | 334天费用、购电、储能和LP约束误差 |
| `summary.json` / `comparison.csv` | 主方案汇总与五组对照 |
| `结果说明.md` / `建模说明.md` | 实际数值、对照解释，以及完整模型假设和公式 |
| `target_table1/2/3.csv`、`target_daily.csv` | 题目指定四天的对应表格 |
| `forecast_diagnostics.csv` | 在线融合权重、历史及发布及融合预测误差 |
| `scenario_trees.json` | 代表日0点树节点、历史样本归属和概率 |
| `run_metadata.json` | 数据指纹、软件版本、参数与假设 |
| `verification.json` | 主方案完整复核结果 |
| `comparisons/` | 各对照方案的可审计明细、汇总与物理费用核验 |
| `figures/` | 费用对照、四天调度、预报融合图 |

Excel保留模板的四个工作表名称和栏目结构；将模板整体后移十分钟的时段表头修正为 `00:00—00:10` 至 `23:50—24:00`，并附单元格注释。原始精度保存在单元格内，仅显示四位小数；四小时充放电汇总严格按24段计算。

“调整购电量”表中最后的费用栏是**净调整费**，不含重复计入的原计划费，也不含紧急费。完整总费用应查逐日CSV或汇总JSON。
