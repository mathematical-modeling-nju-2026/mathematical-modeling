"""生成论文附录的完整源程序清单 tex（自动枚举，避免遗漏/路径错误）。

输出 paper/sections/09a_source_code.tex。
只包含本论文\u5efa模相关的源码：question1~4 的 code/、common/。

收录边界：
  · 只收录\u4ea7生论文数值结果所需的源码（数据读取、建模、求解、核验、汇总）；
  · \u4e0d收录任何绘图/配图代码（各问 plot_*.py、common/plotting/、
    paper/figure_package/、make_figures*.py）——图表属于表达层，
    与数值结果无关；
  · 不含各问 efficiency/ 下的「效率口径对照」代码（def2 敏感性分析专用，
    非主模型）；但保留 common/efficiency/template_layout.py —— 它是主程序读取
    附件5 结果模板表头所必需的公共依赖，并非效率对照专用。
"""
import pathlib
import sys

sys.stdout.reconfigure(encoding='utf-8')

REPO = pathlib.Path(__file__).resolve().parents[1]  # mathematical-modeling
PAPER = REPO / 'paper'

# (组标题, 排序权重, [相对仓库路径, ...])
GROUPS = [
    ('问题一：确定性调度', 1, [
        'question1/code/q1_model.py', 'question1/code/run_q1.py',
    ]),
    ('问题二：滚动随机日前调度', 2, [
        'question2/code/rolling_window.py', 'question2/code/run_experiment.py',
        'question2/code/verify_window.py', 'question2/code/check_information.py',
        'question2/code/report_experiment.py', 'question2/code/make_target_tables.py',
    ]),
    ('问题三：预报融合与场景树多时点调整', 3, [
        'question3/code/q3_data.py', 'question3/code/q3_forecast.py',
        'question3/code/q3_model.py', 'question3/code/run_q3.py',
        'question3/code/verify_q3.py',
    ]),
    ('问题四-2：波动电价下的日前调度', 4, [
        'question4/part2/code/q42_model.py', 'question4/part2/code/run_q42.py',
        'question4/part2/code/verify_q42.py', 'question4/part2/code/check_information.py',
        'question4/part2/code/report_q42.py',
    ]),
    ('问题四-3：波动电价下的多时点调整', 5, [
        'question4/part3/code/q3_data.py', 'question4/part3/code/q3_forecast.py',
        'question4/part3/code/q3_model.py', 'question4/part3/code/run_q3.py',
        'question4/part3/code/verify_q3.py',
    ]),
    ('公共模块：第二问基础数据与 LP（q2_base）', 6, [
        'common/q2_base/q2_data.py', 'common/q2_base/run_1439.py',
    ]),
    ('公共模块：附件5结果模板表头（主程序依赖）', 7, [
        'common/efficiency/template_layout.py',
    ]),
]


def tex_escape_title(s):
    return s.replace('_', r'\_')


def os_path_rel(p, base):
    return str(pathlib.Path(p).relative_to(base))


lines = []
lines.append('% ==================== 附录：完整可运行源程序 ====================')
lines.append('% 按 format2026 第五条要求，附录包含建模所用到的全部完整、可运行的源程序。')
lines.append('% 本文件由 scripts/gen_appendix_source.py 自动生成，勿手改。')
lines.append('% 使用 \\verbatiminput 直接引用仓库源码，与支撑材料逐字一致。')
lines.append(r'\section{建模源程序（完整可运行）}')
lines.append(r'\label{sec:appendix-source}')
lines.append('')
lines.append('以下按问题列出\\textbf{生成论文全部数值结果}所需源程序，')
lines.append('代码与支撑材料 \\texttt{support.zip} 中同名文件\\textbf{逐字一致}；')
lines.append('运行环境与复现命令见 \\S\\ref{sec:appendix-env}。')
lines.append('全部程序使用 Python 语言与 \\texttt{numpy}/\\texttt{scipy}（HiGHS 求解器），')
lines.append('Excel 读写使用 \\texttt{openpyxl}；未使用 SPSS 等需手工交互的软件，')
lines.append('故无交互命令需要单独记录。')
lines.append('')
lines.append('\\textbf{收录边界}：本文的图表由独立的配图脚本从上述程序保存的结果文件')
lines.append('（\\texttt{*.npz}/\\texttt{*.csv}）重建，属于表达层，')
lines.append('不参与任何数值计算，也不影响任何结果；')
lines.append('按“仅收录与建模结果直接相关的源程序”的原则，')
lines.append('各问 \\texttt{plot\\_*.py}、\\texttt{common/plotting/}、')
lines.append('\\texttt{paper/figure\\_package/} 等绘图代码未列入本附录，')
lines.append('其完整文件已随支撑材料一并提交。')
lines.append('')
lines.append(r'\begingroup')
lines.append(r'\footnotesize')
lines.append(r'\setlength{\parindent}{0pt}')
lines.append(r'\setlength{\parskip}{0pt}')
lines.append('')

for idx, (title, weight, files) in enumerate(GROUPS, start=1):
    # 组标题（自动编号，随所在 section 而定）
    lines.append(r'\subsection{%s}' % tex_escape_title(title))
    lines.append('')
    for rel in files:
        src = REPO / rel
        if not src.exists():
            print(f'[警告] 文件不存在: {rel}')
            continue
        # 相对 paper/ 的路径（编译时以 paper/ 为工作目录，故前缀 ../）
        rel_to_paper = '../' + rel.replace('\\', '/')
        name = src.name
        lines.append(r'\subsubsection*{%s}' % tex_escape_title(name))
        lines.append(r'\verbatiminput{%s}' % rel_to_paper)
        lines.append('')


lines.append(r'\endgroup')

out = PAPER / 'sections' / '09a_source_code.tex'
out.write_text('\n'.join(lines), encoding='utf-8')
print(f'已生成 {out}')
print(f'  共 {sum(len(f) for _,_,f in GROUPS)} 个文件引用')
