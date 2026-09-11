# 第4问4-2

基于 CShen/方案B_滚动窗口优化 的推荐Q2，计算附件4波动电价下的计划购电、储能和紧急购电。只处理4-2，不改动既有Q2或Q3。

题面未说明电价发布时间。本目录默认主模型只用历史电价预测；同时保存当日电价在0:00已知的完整对照。主模型当前为联合场景模型，平均电价近似也单独保存，实际费用比较见结果说明。

## 阅读和结果

- 建模说明.md：信息条件、预测、联合场景、LP、执行计费和约束推导。
- 结果说明.md：真实计算结果、费用比较及局限。
- 指定日期结果.md：题目四个指定日期的表1、表2、表3。
- result4-2.xlsx：默认主模型，三个工作表均覆盖2—12月。
- variants/mean_price/result4-2.xlsx：仅使用场景平均电价的简化对照。
- variants/known_today_price/result4-2.xlsx：当日电价已知的对照。
- variants/q2_repriced/result4-2.xlsx：优化Q2原计划按附件4重新结算。

统计期为2025年2月1日至12月31日，共334天。所有方案共享Q2的1月预热，从1月1日6000 kWh到2月1日8550 kWh；1月费用不计入统计。原始附件按区间末解释，导出纠正模板表头十分钟错位，保留工作表及列结构。

## 复现

在 E:\math_model 下按顺序运行：

    .\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/C_yang/ques4_2/run_q42.py
    .\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/C_yang/ques4_2/verify_q42.py
    .\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/C_yang/ques4_2/check_information.py
    $env:MPLCONFIGDIR='E:/math_model/.cache/matplotlib'
    .\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/C_yang/ques4_2/report_q42.py

依赖：numpy、scipy、pandas、openpyxl、matplotlib。没有随机抽样，无需随机种子。当前仓库的优化Q2代码及其原始方案B是导入依赖，路径均相对仓库解析。

若论文明确假设0:00已知当日电价，运行入口可加参数 --primary known_today_price；随后仍按顺序核验、生成报告。所有对照都计算，参数只决定根目录发布哪套结果。

## 文件与改动目的

| 文件 | 用途 |
|---|---|
| q42_model.py | 读取附件4，1月选择价格预测器，生成价格—净负载场景，扩展原Q2目标函数 |
| run_q42.py | 共同预热、完整回测、实际价格结算、保存四套结果和Excel |
| verify_q42.py | 独立读取附件2/4检查物理与费用，复用已有独立Excel核验器 |
| check_information.py | 解析小例、退化到Q2、未来数据扰动检查 |
| report_q42.py | 核验通过后发布主结果、指定日期表格及图表 |
| 建模说明.md、结果说明.md、README.md | 模型解释、实际结论和复现方法 |
| daily_summary.csv、schedule_detail.csv.gz、summary.json | 根目录主模型逐日、逐段和汇总数据 |
| variants/ | 四套方案的完整结果，避免只展示一套费用 |
| price_training_scores.csv、price_data_summary.json | 1月选择依据和正式统计期价格预测误差 |
| forecast_archive.npz | 已按历史边界生成的预测与残差档案；其中实际值仅供结算与核查 |
| january_warmup.csv.gz、january_summary.csv | 共同1月策略及状态来源，价格预测器没有参与该预热决策 |
| comparison.csv、monthly_comparison.csv | 同一实际电价下的费用比较 |
| target_days/、指定日期结果.md | 四个指定日期的计划购电、储能及完整紧急区间表 |
| verification.json、information_verification.json、publication_verification.json | 独立核验、因果检查及发布文件一致性 |
| source_fingerprints.json、run_metadata.json | 依赖指纹、参数、信息条件及统计口径 |
| figures/ | 费用与月度收益、指定日价格预测、储能调度图，提供PNG/PDF |

最小改动对照是“平均电价模型”；联合场景保留同一时段价格和缺口的依赖。当日电价已知单列为信息条件对照，不当作历史预测算法的优势。没有引入场景树、日内调整或负载/光伏新预测器，因为它们会改变本轮继承Q2的比较范围。
