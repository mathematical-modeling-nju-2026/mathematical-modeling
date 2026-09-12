# 数学建模最终方案

按指定方案整理，数学逻辑和已保存结果保持不变。已有结果已由团队复现；本次检查聚焦文件搬迁、路径、导入和输入读取。

| 问题 | 最终方案来源 | 说明 | 正式结果 |
|---|---|---|---|
| 1 | 原 `C_yang/q1` | [建模](question1/建模说明.md) · [结果](question1/结果说明.md) | [result1.xlsx](question1/results/result1.xlsx) |
| 2 | 原 `CShen/方案B_滚动窗口优化`，有效残差56天等权 | [建模](question2/建模说明.md) · [结果](question2/结果说明.md) | [result2.xlsx](question2/results/result2.xlsx) |
| 3 | 原 `CShen/问题三_优化探索`，按其最终报告补齐1402.24万元主方案 | [建模](question3/建模说明.md) · [结果](question3/结果说明.md) | [result3.xlsx](question3/results/result3.xlsx) |
| 4-2 | 原 `C_yang/ques4_2`，联合电价场景 | [建模](question4/part2/建模说明.md) · [结果](question4/part2/结果说明.md) | [result4-2.xlsx](question4/part2/results/result4-2.xlsx) |
| 4-3 | 原 `CShen/方案B_问题4_第三问重模拟` | [建模](question4/part3/建模说明.md) · [结果](question4/part3/结果说明.md) | [result4-3.xlsx](question4/part3/results/result4-3.xlsx) |

```text
question1/                建模说明、结果说明、code/、results/（含 figs/）、efficiency/
question2/                建模说明、结果说明、code/、results/（含 figures/ 及候选对照）、efficiency/
question3/                建模说明、结果说明、code/、results/、research/（指定探索目录）、efficiency/
question4/                建模说明、结果说明、part2/、part3/、efficiency/
common/q2_base/           第二问与4-2共用基础LP、数据读取及历史基准
common/plotting/          已有绘图样式和导出函数
common/efficiency/        两种「90% 效率」口径的定义、校验与汇总（见 EFFICIENCY.md）
data/                    C题题面、附件1—4及附件5原模板
archive/                 未采用方案、旧文档、冒烟产物与缓存
docs/                    整理报告、逐文件迁移清单、核验记录
tools/validate_layout.py  目录迁移检查入口，不重跑优化
```

## 「90% 效率」两口径研究

题目附录 1 只写「充放电效率为 90%」，存在两种合理解读：
往返效率 **0.81**（充/放各 90%）与 **0.90**（放电量/充电量 = 90%，国标）。
四问均已按两口径重跑并对照，总费用下降 **3.16%–3.77%**。

- 总说明：[EFFICIENCY.md](EFFICIENCY.md)
- 汇总结果：[common/efficiency/output/](common/efficiency/output/)（对照表 + 四问题目指定日期表）
- 一键汇总：`python -X utf8 common/efficiency/compare.py`
- 各问细节：`question{1..4}/efficiency/README.md`

> `def1_side90` 与原口径逐值相同（明细 48,096 行差异 `0.00e+00`），
> 故不另存副本：其「结果目录」就是 `questionN/results/`；
> `def2_roundtrip90` 的结果在 `questionN/efficiency/results/`。
> **原有模型代码与结果零改动**。

`modelviz-skill/` 是独立工具项目，保持原位；`CUMCM2026Problems/` 是本地原题资料（原有Git忽略规则保留），最终程序统一读取已纳入仓库的 `data/`。

## 环境与运行

```powershell
python -m pip install -r requirements.txt
python -X utf8 tools/validate_layout.py
```

四问复现命令见各问README。第一问为典型日；其余统计2025年2—12月，勿混合初始化和电价口径。第三问主结果不应用同年扫描得到的 `k=0.92`；探索材料完整保留。

路径修改不重新背书旧实验结论。全部移动、文档合并、未采用方案处理、已知缺件及验证范围见 [整理报告](docs/整理报告.md)。逐文件来源和原SHA256见 [迁移清单](docs/migration_manifest.json)，历史基准提交也记录在该清单。
