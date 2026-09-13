# 论文材料

当前供新稿使用的是 [独立图包](figure_package/README.md)：[图文预览PDF](figure_package/图文预览.pdf)、[浏览器预览](figure_package/图文预览.html)、[图注与正文描述](figure_package/图注与正文.md)。十张主图统一样式，均由各问保存结果重新组织生成。

原 `main.tex`、`main.pdf`、`sections/` 和 `figs/` 保留作旧稿资料。下面是旧稿的编译说明；新图包的重绘与使用方法见上方入口。

# 旧稿编译说明

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

第三问与4-3的图按各自保存的CSV重绘，并同步到本论文（从任意工作目录使用脚本路径运行）：

```powershell
python -X utf8 paper/refresh_q3_figures.py
```

此命令不重算优化，更新 `q3_cost.pdf`、`q3_dispatch.pdf`、`q3_fusion.pdf`、`q43_cost.pdf` 和 `q43_dispatch.pdf`；输入与图片SHA256记录在 `figs/q3_figure_sources.json`。费用和调度图分别使用固定电价、波动电价结果。两问共享同一光伏预测器与诊断数据，因此预报融合曲线相同是正常的，论文仅在第三问展示。更新图片后仍需按以下方式重新编译 `main.pdf`。

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
| **正文（含参考文献）** | 2–31 | **30** | **不超过 30 页** ✓ |
| 附录 | 32–161 | 130 | 页数不限 ✓ |

## 格式规范对照

| 规范要求 | 本文实现 |
|---|---|
| A4 纸，页边距 ≥2.5 cm | `geometry`: 上下左右均为 2.5 cm ✓ |
| 摘要页含标题与关键词 | 见 `00_abstract.tex`，正文四问共 5 段、共占 1 页 ✓ |
| 页码从摘要页起、页脚居中 | `fancyfoot[C]{\thepage}`，摘要页为 1 ✓ |
| 正文不超 30 页 | 30 页 ✓ |
| 附录源代码不越出页边界 | 折行至 70 显示列（中文算 2 列）；实测无越界 ✓ |
| 首行缩进两格 | `\setlength{\parindent}{2\ccwd}`（两个汉字宽）✓ |
| 中文双引号 | 全文使用 “ ”（U+201C/U+201D）成对 ✓ |
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
5. **引号写法**：源码中请直接使用中文弯引号 “ ”（U+201C/U+201D），
   **不要**使用直引号 `"`——LaTeX 会把直引号一律渲染为后引号 ” 。
6. **首行缩进**：依赖 `main.tex` 中的 `\parindent = 2\ccwd`；
   若某段不需缩进（如紧跟公式的说明），用 `\noindent` 显式取消。
