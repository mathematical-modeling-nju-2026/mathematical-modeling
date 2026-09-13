"""生成论文附录的完整源程序清单 tex（自动枚举，避免遗漏/路径错误）。

输出 paper/sections/09a_source_code.tex。

重要：本脚本直接引用 `final_version/支撑材料/` —— 即最终提交的支撑材料文件夹
—— 中的源码文件，因此附录与支撑材料同名文件**逐字一致**是结构性保证，
不需要任何人工同步。

收录边界：
  · 收录建模相关的全部源程序（数据读取、建模、求解、核验、汇总）；
  · 不收录绘图/配图代码（各问 plot_*.py、common/plotting/）——
    它们属于表达层，只从已保存的结果文件重建图表，不参与数值计算；
  · 不含各问 efficiency/ 下的「效率口径对照」代码（敏感性分析专用，
    非主模型）；但保留 common/efficiency/template_layout.py —— 它是主程序
    读取附件5 结果模板表头所必需的公共依赖。
"""
import pathlib
import sys

sys.stdout.reconfigure(encoding='utf-8')

REPO = pathlib.Path(__file__).resolve().parents[1]  # mathematical-modeling
PAPER = REPO / 'paper'
FV = REPO / 'final_version' / '支撑材料'             # 支撑材料文件夹

# (组标题, [相对 FV 的路径, ...])
GROUPS = [
    ('问题一：确定性调度', [
        'Q1/q1_code/q1_model.py', 'Q1/q1_code/run_q1.py',
    ]),
    ('问题二：滚动随机日前调度', [
        'Q2/code/rolling_window.py', 'Q2/code/run_experiment.py',
        'Q2/code/verify_window.py', 'Q2/code/check_information.py',
        'Q2/code/report_experiment.py', 'Q2/code/make_target_tables.py',
    ]),
    ('问题三：预报融合与场景树多时点调整', [
        'Q3/code/q3_data.py', 'Q3/code/q3_forecast.py',
        'Q3/code/q3_model.py', 'Q3/code/run_q3.py',
        'Q3/code/verify_q3.py',
    ]),
    ('问题四-2：波动电价下的日前调度', [
        'Q4/part2/code/q42_model.py', 'Q4/part2/code/run_q42.py',
        'Q4/part2/code/verify_q42.py', 'Q4/part2/code/check_information.py',
        'Q4/part2/code/report_q42.py',
    ]),
    ('问题四-3：波动电价下的多时点调整', [
        'Q4/part3/code/q3_data.py', 'Q4/part3/code/q3_forecast.py',
        'Q4/part3/code/q3_model.py', 'Q4/part3/code/run_q3.py',
        'Q4/part3/code/verify_q3.py',
    ]),
    ('公共模块：第二问基础数据与 LP（q2_base）', [
        'common/q2_base/q2_data.py', 'common/q2_base/run_1439.py',
    ]),
    ('公共模块：附件5结果模板表头（主程序依赖）', [
        'common/efficiency/template_layout.py',
    ]),
]


def tex_escape_title(s):
    return s.replace('_', r'\_')


lines = []
lines.append('% ==================== 附录：完整可运行源程序 ====================')
lines.append('% 按 format2026 第五条要求，附录包含建模所用到的完整、可运行的源程序。')
lines.append('% 本文件由 scripts/gen_appendix_source.py 自动生成，勿手改。')
lines.append('% 源码直接取自支撑材料文件夹 final_version/支撑材料/，故与所提交文件逐字一致。')
lines.append(r'\section{建模源程序（完整可运行）}')
lines.append(r'\label{sec:appendix-source}')
lines.append('')
lines.append('以下按问题列出\\textbf{生成论文全部数值结果}所需源程序。')
lines.append('这些代码\\textbf{直接取自支撑材料文件夹 \\texttt{final\\_version/\\allowbreak 支撑材料/}}，')
lines.append('因此与所提交文件\\textbf{逐字一致}；')
lines.append('运行环境与复现命令见 \\S\\ref{sec:appendix-env}。')
lines.append('全部程序使用 Python 语言与 \\texttt{numpy}/\\texttt{scipy}（HiGHS 求解器），')
lines.append('Excel 读写使用 \\texttt{openpyxl}；未使用 SPSS 等需手工交互的软件，')
lines.append('故无交互命令需要单独记录。')
lines.append('')
lines.append('\\textbf{收录边界}：本文的图表由配图脚本从上述程序保存的结果文件')
lines.append('（\\texttt{*.npz}/\\texttt{*.csv}）重建，属于表达层，')
lines.append('不参与任何数值计算，也不影响任何结果；')
lines.append('按“仅收录与建模结果直接相关的源程序”的原则，')
lines.append('\\texttt{plot\\_*.py} 与 \\texttt{common/plotting/} 未列入本附录，')
lines.append('其完整文件已随支撑材料一并提交。')
lines.append('')
lines.append(r'\begingroup')
lines.append(r'\footnotesize')
lines.append(r'\setlength{\parindent}{0pt}')
lines.append(r'\setlength{\parskip}{0pt}')
lines.append('')

count = 0
for title, files in GROUPS:
    lines.append(r'\subsection{%s}' % tex_escape_title(title))
    lines.append('')
    for rel in files:
        src = FV / rel
        if not src.exists():
            print(f'[警告] 文件不存在: final_version/支撑材料/{rel}')
            continue
        # 编译时以 paper/ 为工作目录，故前缀 ../final_version/支撑材料/
        rel_to_paper = '../final_version/支撑材料/' + rel
        name = src.name
        lines.append(r'\subsubsection*{%s}' % tex_escape_title(name))
        lines.append(r'\verbatiminput{%s}' % rel_to_paper)
        lines.append('')
        count += 1

lines.append(r'\endgroup')

out = PAPER / 'sections' / '09a_source_code.tex'
out.write_text('\n'.join(lines), encoding='utf-8')
print(f'已生成 {out}')
print(f'  引用 final_version/支撑材料/ 下 {count} 个源程序文件')
print('  与支撑材料逐字一致（同一文件）')
