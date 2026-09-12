# 第一问交付与复现

主要结论：全天外购 **59482.70 kWh**，购电费 **35126.95 元**，比无储能节省 **26.90%**；初末电量均为 **6000 kWh**。效率取充、放电各 90%，采用右端点时间口径，允许弃光、不售电。

先读 [结果说明.md](结果说明.md) 查看模型、假设、结果与解释；题目指定格式的数字见 [paper_tables.md](paper_tables.md)，提交工作簿为 [result1.xlsx](result1.xlsx)。

**在 PowerShell 中复现**

本次已在 `ques1/.venv` 安装依赖。进入本目录后，依次运行：

```powershell
.\.venv\Scripts\python.exe solve.py
.\.venv\Scripts\python.exe verify.py
.\.venv\Scripts\python.exe plot_results.py
```

也可以从任意工作目录用脚本的绝对路径运行。输入和输出均相对脚本自身定位。

其他电脑需 Python 3.11 或兼容版本，先创建环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

绘图需要本机可用的中文字体，如黑体、微软雅黑或 Noto Sans CJK SC。本次实际使用 SimHei。无需安装建模技能即可运行，绘图辅助代码已复制到本目录。

脚本会覆盖本目录下由它生成的同名结果文件。`结果说明.md` 为本次参数与计算结果的说明，修改参数后应同步更新其中的人工解释和数字。`paper_tables.md` 则由求解脚本自动生成。

**文件与用途**

| 文件 | 内容与用途 |
|---|---|
| `solve.py` | 读取附件 1，检查数据与时间，构建并求解 LP/MILP；生成模板工作簿、完整调度、汇总和论文表格 |
| `verify.py` | 直接核查原始附件与落盘结果，用另一种累计电量 LP 复算费用；生成核验报告 |
| `plot_results.py` | 根据真实 CSV 绘制调度总览与费用对比，导出 PNG/PDF |
| `setup_style.py` | 从 cumcm-plotting 技能复制的字体和图表样式工具，保障中文显示和可移植运行 |
| `export_figure.py` | 从同一技能复制的多格式导出工具，固定图片物理尺寸与 300 DPI |
| `requirements.txt` | 本次实际使用的五项直接依赖及版本 |
| `.gitignore` | 忽略本目录虚拟环境、字节码与字体缓存 |
| `result1.xlsx` | 保留模板的“计划购电量”“充放电量”两张表，填入题目要求结果 |
| `dispatch_detail.csv` | 144 时段原始输入、决策、储电量、费用及无储能对照；UTF-8 BOM 编码便于 Excel 阅读 |
| `summary.json` | 参数、数据检查、源文件哈希、求解状态、成本指标、六段汇总与模板修正记录 |
| `verification.json` | 54 项数值检查、源文件哈希核对、独立约束实现下的最优费用 |
| `paper_tables.md` | 与题面表 1、表 2 对应的 Markdown 表格 |
| `结果说明.md` | 建模公式、假设、最终表格、调度解释、核验证据和未采用方案 |
| `figures/dispatch_overview.png`、`.pdf` | 电价、负载与光伏、购电、充放电和内部储电量的五面板图 |
| `figures/cost_comparison.png`、`.pdf` | 全天费用及累计费用曲线对比 |
| `README.md` | 本文件，说明复现步骤和产物用途 |

`.venv/` 是本次创建的运行环境，`.mplconfig/` 和 `__pycache__/` 是运行缓存，不属于题目提交结果。

**明细字段**

| 字段 | 含义 |
|---|---|
| `period`、`interval` | 时段编号 1—144、当天起止时间 |
| `start_minute`、`end_minute` | 距当天 0:00 的起止分钟数 |
| `price_yuan_per_kwh` | 该时段电价，元/kWh |
| `load_kw`、`pv_kw` | 附件中的负载、光伏预测功率，kW |
| `load_kwh`、`pv_kwh` | 上述功率乘以 1/6 h 后的电量 |
| `grid_kwh` | 计划外购电量 |
| `charge_kwh`、`discharge_kwh` | 储能设备外部输入、输出电量，均为非负数 |
| `curtailment_kwh` | 弃光电量 |
| `energy_start_kwh`、`energy_end_kwh` | 每个时段开始、结束时的电池内部电量 |
| `soc_end` | 时段末储电量除以额定容量 12000，范围 0.1—0.9 |
| `cost_yuan` | 电价乘以计划购电量 |
| `no_storage_grid_kwh`、`no_storage_cost_yuan` | 同输入下无储能方案的购电量和费用 |
| `mode` | 按 $10^{-6}$ kWh 容差识别的充电、放电或待机 |

**输出时间标签**

输入 00:10 映射到 00:00—00:10，输入 0:00+1 映射到 23:50—24:00。原模板时间从 00:10 开始且延伸到次日 00:10，本次仅在输出副本中纠正该错位。论文指定的 10:00—10:10 取输入时间戳 10:10 对应的数据，而非 10:00 那一行。

表格显示两位或六位小数不改变 Excel 内部数值精度。不要把舍入后的两位小数作为设备派发数据重新计算能量守恒。
