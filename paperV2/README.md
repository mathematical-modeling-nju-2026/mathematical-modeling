# 论文稿（paperV2）编译与资产校验说明

本目录是一份自包含、可编译的中文竞赛论文稿。正文、图表、指定结果表与五份交付
工作簿均已齐备，`main.tex` 经两遍 XeLaTeX 编译即得 `main.pdf`。本文件即附录
「支撑材料与复现说明」中所称的“本稿说明文件”，记录编译方式与资产校验过程。

## 文件结构

```
paperV2/
├── main.tex                 主文件（宏包、版式、摘要、\input 各章节、参考文献）
├── README.md                本说明文件
├── prepare_assets.py        资产生成脚本（只读已保存结果，不调用优化器）
├── source_manifest.json     来源与产物的 SHA-256 记录 + 算数核验清单
├── sections/                正文章节
│   ├── 01_framework.tex     问题重述、统一假设与符号
│   ├── 02_question1.tex     问题一
│   ├── 03_question2.tex     问题二
│   ├── 04_question3.tex     问题三
│   ├── 05_question4.tex     问题四（4-2、4-3）
│   ├── 06_validation.tex    模型检验与效率口径对照
│   ├── 07_conclusion.tex    结论
│   └── 08_appendix.tex      指定时段/日期完整结果 + 支撑材料与复现说明
├── tables/                  各问费用/对照表与题目表1/2/3（target_results.tex）
├── figures/                 十张主图（.tex 图注 + .pdf/.png）
├── data/                    prepare_assets.py 落盘的中间 CSV
└── deliverables/            五份正式结果工作簿（自各问 results/ 复制，未改动）
```

## 编译方法

需 XeLaTeX（不能用 pdfLaTeX，因需中文支持与 `fontspec`）。`main.tex` 使用
`fontset=windows`，依赖 Windows 中文字体（宋体 SimSun、黑体 SimHei）。

在 `paperV2/` 目录执行（**跑两遍**以生成交叉引用）：

```powershell
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
```

输出为 `main.pdf`。

> Linux 上若无 Windows 字体，任选其一：
> 1. 安装 SimSun/SimHei（如从 Windows 拷贝到 `~/.fonts` 后 `fc-cache -fv`）；
> 2. 或把 `main.tex` 首行的 `fontset=windows` 改为 `fontset=fandol`
>    （TeX Live 自带 Fandol 字体，无需额外安装）。
> 两种方式只影响字体外观，不改动正文与数字。

## 资产生成与校验

图表、指定结果表、`data/` 与 `deliverables/` 均由 `prepare_assets.py` 从**已保存
结果**读取生成，**不调用任何优化器**：

```powershell
python -X utf8 prepare_assets.py
```

脚本要点：

- 仅读取题面 `data/C题.pdf`、各问 `建模说明.md` 与 `code/`、公共 `common/q2_base`、
  新图包 `paper/figure_package`、效率补充材料 `paper/extra`，以及各问
  `results/` 下的保存结果；用 SHA-256 固定来源与产物对应关系。
- 生成十张图的 `.tex` 图注、九张表、`target_results.tex`（题目表 1/2/3 的指定
  时段购电、四小时充放电、连续紧急购电区间）与五份工作簿副本。
- 末尾断言约 50 项算数核验（各问主结果、费用分解、指定日期储能递推与紧急量、
  效率对照的转录一致性），全部通过才会重写 `source_manifest.json`。

`source_manifest.json` 记录 `source_sha256`、`output_sha256`、`checks`、
`required_dates` 与 `scope`。其中 `scope` 明确声明：不重跑优化；效率对照数字仅
转录自 `paper/extra`；4-3 优化目标与实际结算的附加项差异已在正文披露。

## 交付工作簿

`deliverables/` 下为五份未改动的正式结果：

| 文件 | 对应问题 |
|---|---|
| `result1.xlsx` | 问题一 |
| `result2.xlsx` | 问题二 |
| `result3.xlsx` | 问题三 |
| `result4-2.xlsx` | 问题四-2 |
| `result4-3.xlsx` | 问题四-3 |

## 效率口径说明

正文主线采用“充电、放电效率各 0.9”（往返 0.81）；另一“往返 0.90”口径仅作为
稳健性检验列于 `tables/efficiency.tex`，不进摘要。两者定义与复现见根目录
`EFFICIENCY.md`。

## 注意事项

1. 修改正文后务必重新编译两遍，否则交叉引用与页码不更新。
2. 源码直接使用中文弯引号 “ ”（U+201C/U+201D），不要用直引号 `"`。
3. 数字口径：第一问为典型日；其余各问统计 2025 年 2—12 月（1 月用于预热），
   勿混用初始化与电价口径。
