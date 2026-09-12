# 方案B滚动窗口优化

本目录保留全部候选结果。推荐改动是：**剔除负载预测器尚不能使用同星期历史时产生的回退残差，仍采用最近56天等权场景**。近期加权和在线选窗的收益不稳健，未将其作为最终替换策略。

原 `../方案B_1439万/run_1439.py` 被导入使用，预测与LP不复制、不重构、不修改。附件1读取仅在进程内缓存。全部对照共享原等权1月预热，2月初8550 kWh、年末6000 kWh。

费用统计期为2025年2—12月334天，不计1月预热费用。推荐方案由14,401,996.98元降至14,389,135.08元，按未舍入值节省12,861.89元（0.0893%）。差异只出现在启动阶段，3月5日至年末逐日费用与原方案一致；尚无另一个年份的独立验证。

前7天回退残差本身是合法的因果预测误差。“有效历史筛选”在这里指区分回退预测与具有同星期历史的预测器产生的残差，并非修复错误的残差数值。

## 复现

从 `E:\math_model` 使用已有虚拟环境：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/run_experiment.py
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/run_experiment.py --extended --only uniform28 uniform42 online_extended --out extensions/short_windows
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/run_experiment.py --first-residual 7 --initial 8550 --only uniform56 half_life28 online_primary --out sensitivity/valid_residuals
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/verify_window.py
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/verify_window.py --root mathematical-modeling/CShen/方案B_滚动窗口优化/extensions/short_windows
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/verify_window.py --root mathematical-modeling/CShen/方案B_滚动窗口优化/sensitivity/valid_residuals
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/check_information.py
$env:MPLCONFIGDIR='E:/math_model/.cache/matplotlib'
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/report_experiment.py
```

依赖：numpy、scipy、pandas、openpyxl、matplotlib。`--days`只供短期冒烟运行，截断日不执行年末SOC条件；不应当作全年比较。

只复现推荐方案，可运行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 mathematical-modeling/CShen/方案B_滚动窗口优化/run_experiment.py --first-residual 7 --only uniform56 --out recommended_only
```

默认会从1月1日6000 kWh运行统一预热，再从其期末状态开始报告；不是无依据地把2月初SOC设为8550。

## 方法

固定候选：56天等权、56天内半衰期7/14/28天指数加权；扩展候选为28天和42天等权。所有权重归一化为1，保持5倍紧急电价不变。

对历史场景 $i$，以距昨天的天数 $a_i$ 定义

$$w_i=\frac{2^{-a_i/h}}{\sum_j2^{-a_j/h}}.$$

指数加权不会增加场景数；56天时的有效样本量依次约为20.06、35.65、48.48（等权为56），近期敏感性提高的同时，尾部估计更不稳定。

每周选窗：从2月1日起，每7天用此前最多28个完成日的价格加权0.8分位损失选择候选。每个历史日的预测和场景只由当时已知数据生成。最少14个有效评分日；原样本口径首次有24个评分日，排除前7天回退残差后首次有23个评分日。后者2月1日用于优化的残差场景仍为24条，场景数与历史评分日数不同。平分按固定候选顺序，历史不足回退等权。

评分为 $\sum_t p_t\rho_{0.8}(N_t-q_t)$，其中 $q_t$ 是不低于点预测的场景80%分位。它来自

$$p_tz_t+5p_t(N_t-z_t)_+=p_tN_t+5p_t\rho_{0.8}(N_t-z_t).$$

但评分未完整计入储能耦合，故分位损失更小不保证实际调度总费用更小。固定 $c,d$ 时，完整LP的供给还必须满足 $z\ge d-c$（购电非负）；80%分位不能作为所有时段无条件的等式。

原模型的充放电在所有场景中共享，紧急损失逐时段可分，因此目标只依赖各时段加权边缘误差分布。保留整日残差便于组织样本，**其时间相关性本身不是本版本收益来源**。

## 文件与改动原因

| 文件 | 内容与用途 |
|---|---|
| `rolling_window.py` | 导入原预测器/LP，增加场景权重、有效历史过滤、历史分位评分与每周选择 |
| `run_experiment.py` | 统一预热、逐日执行、保存全部方案、准确导出分时段及弃电量 |
| `verify_window.py` | 独立读取原附件，复算物理、费用及Excel，防止共用结算错误 |
| `check_information.py` | 未来数据扰动、周内选择锁定和解析LP小例 |
| `report_experiment.py` | 确认全部核验通过后，汇总成功及失败的候选，发布推荐文件并绘图 |
| `result2.xlsx`、`daily_summary.csv`、`schedule_detail.csv.gz` | 推荐有效残差等权方案；时段标签和4小时汇总经过反读验证 |
| `summary.json` | 推荐结果、收益及源方案路径 |
| `结果说明.md` | 实际费用、收益来源、推荐理由及局限 |
| `variants/` | 第一轮5组原样本口径候选 |
| `extensions/short_windows/` | 短窗口及六候选在线选择，共3组 |
| `sensitivity/valid_residuals/` | 排除回退残差后的配对试验，共3组 |
| `comparison.csv`、`all_comparisons.csv`、`monthly_savings.csv` | 第一轮、全部实验及月度收益明细 |
| `prequential_scores.csv`、`prequential_quantiles.npz` | 当时可产生的候选预测及其实现后的损失，便于核对在线选择 |
| `common_january.json`、`run_metadata.json`、`source_fingerprints.json` | 公共预热、参数口径与依赖文件指纹 |
| `verification*.json`、`information_verification.json` | 独立验证报告，含原基线复现与发布文件一致性 |
| `figures/window_comparison.png/.pdf` | 费用增减与累计收益，显示改善集中于年初 |

原目录的日弃电字段采用“先日汇总再截断”，不能代表逐时弃电总量。新导出按每段正剩余求和；这是单独的报表修正，不改变优化或费用。原模板整体后移十分钟的表头也在新文件中纠正，原文件保持原样。

没有采用“事后挑每一天最便宜候选”的神谕策略；未提高日内调整频率、延长前瞻、改变预测器或混入第三问外部预报。实验表明本轮首先应处理有效历史样本，继续增加窗口参数没有稳定收益证据。
