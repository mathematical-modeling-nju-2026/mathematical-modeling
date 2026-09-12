# 论文编译说明

## 环境要求

- **XeLaTeX**（必须用 XeLaTeX，不能用 pdfLaTeX，因为需要中文支持与 `fontspec`）
- 中文字体：Windows 系统字体（宋体 SimSun、黑体 SimHei、楷体 KaiTi）
- 本机参考配置：TeX Live 2026，安装于 `D:\texlive\2026`

### 所需宏包

```powershell
# 若缺少宏包，用 tlmgr 补装（清华镜像）
& "D:\texlive\2026\bin\windows\tlmgr.bat" install `
    xetex xecjk ctex fandol pgf siunitx tabularx makecell `
    titlesec tools ms float multirow mathtools amsfonts `
    fancyhdr hyperref enumitem setspace xcolor subcaption booktabs
```

## 编译方法

在 `paper/` 目录下执行（**需跑两遍**以生成交叉引用与页码）：

```powershell
$bin = "D:\texlive\2026\bin\windows"
cd paper
& "$bin\xelatex.exe" -interaction=nonstopmode main.tex
& "$bin\xelatex.exe" -interaction=nonstopmode main.tex
```

输出为 `main.pdf`。

## 文件结构

```
paper/
├── main.tex                 主文件（宏包、版式、\input 各章节）
├── main.pdf                 编译产物
├── make_q2_fig.py           生成 q2_trend.pdf 的脚本
├── figs/                    插图（PDF 矢量图，来自各问 results/figures）
│   ├── q1_dispatch.pdf      问题一调度图
│   ├── q1_comparison.pdf    问题一费用对比
│   ├── q2_trend.pdf         问题二费用趋势（本目录脚本生成）
│   ├── q3_cost.pdf          问题三费用与紧急电量对照
│   ├── q3_dispatch.pdf      问题三指定日调度
│   ├── q3_fusion.pdf        问题三融合权重演化
│   ├── q42_prices.pdf       问题四-2 电价曲线
│   ├── q42_cost.pdf         问题四-2 费用对照
│   ├── q43_cost.pdf         问题四-3 费用对照
│   └── q43_dispatch.pdf     问题四-3 指定日调度
└── sections/                各章节正文
    ├── 00_abstract.tex      摘要（独立一页）
    ├── 01_restatement.tex   问题重述与分析
    ├── 02_assumptions.tex   模型假设
    ├── 03_q1.tex            问题一
    ├── 04_q2.tex            问题二
    ├── 05_q3.tex            问题三
    ├── 06_q4.tex            问题四
    ├── 07_evaluation.tex    模型评价与推广
    ├── 08_references.tex    参考文献
    └── 09_appendix.tex      附录（支撑材料清单、环境、代码、核验）
```

## 页数结构（符合竞赛规范）

| 部分 | 页码 | 页数 | 规范要求 |
|---|---|---|---|
| 摘要专用页 | 1 | 1 | 不超过 1 页 ✓ |
| **正文** | 2–28 | **27** | **不超过 30 页** ✓ |
| 附录 | 29–36 | 8 | 页数不限 ✓ |

## 格式规范对照

| 规范要求 | 本文实现 |
|---|---|
| A4 纸，页边距 ≥2.5 cm | `geometry`: 上下 2.6 cm、左右 2.7 cm ✓ |
| 摘要页含标题与关键词 | 见 `00_abstract.tex` ✓ |
| 页码从摘要页起、页脚居中 | `fancyfoot[C]{\thepage}`，摘要页为 1 ✓ |
| 正文不超 30 页 | 27 页 ✓ |
| 附录含支撑材料清单与完整源程序 | 见 `09_appendix.tex` 附录 A、C ✓ |
| 无参赛者身份/学校信息 | 全文未出现 ✓ |
| 参考文献规范标注 | `08_references.tex`，正文用 `\cite` ✓ |

## 注意事项

1. **电子版提交**：本 `main.pdf` 即为电子版论文，**首页是摘要页**，
   不含承诺书与编号专用页（符合规范第十条）。
2. **纸质版**：需在摘要页前**手工加**承诺书与编号专用页（由赛区提供），
   论文正文与附录一并打印装订。
3. **支撑材料**：单独压缩为 `support.zip`（含源程序、结果文件、数据），
   文件列表见论文附录 A。
4. **修改正文后务必重新编译两遍**，否则交叉引用与页码会不更新。
