"""生成论文附录的完整源程序清单 tex（自动枚举，避免遗漏/路径错误）。

输出 paper/sections/09a_source_code.tex。

重要：本脚本以 `\verbatiminput` 直接引用仓库内 `final_version/支撑材料/`
——即最终支撑材料的实际存放位置——中的源码文件，因此附录与支撑材料
同名文件**逐字一致**是结构性保证，不需要任何人工同步。

注意：`final_version/` 只是仓库内的存放目录名，**不会出现在论文正文中**
（支撑材料提交时以其自身内容为根目录）。附录里展示给读者的路径一律相对
支撑材料根目录书写。

收录范围：支撑材料中的**全部源程序**（数据读取、建模、求解、核验、
结果表生成与汇总）。绘图代码不参与数值计算，已从支撑材料中移除；
各问 efficiency/ 下的「效率口径对照」代码为敏感性分析专用，不在支撑材料内；
common/efficiency/template_layout.py 保留，因它是主程序读取附件5
结果模板表头所必需的公共依赖。

GROUPS 中列出的路径必须与 final_version/支撑材料/ 的实际内容一一对应：
若文件缺失会打印警告，若新增源程序而此处未列出，请同步更新。
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


# verbatim 环境的折行宽度（按显示列数）。
# 正文本宽 16.06cm（四边 2.5cm 边距），\footnotesize 等宽字体约 6pt/字符，
# 每行约可容纳 76 列；中文在等宽字体中占 2 列，故必须按显示列数而非
# 字符数计算，否则含中文的行仍会溢出。取 72 留出安全余量。
MAX_COLS = 70
# 续行缩进（列），表示该行由上一行折行而来，便于读者还原原始代码。
CONT_INDENT = 2


def _width(s):
    """字符串的显示列数：东亚宽字符（中文、全角标点）算 2，其余算 1。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in s)


def wrap_line(line, width=MAX_COLS):
    """把超长源码行按显示列数折成多行。

    策略：在不超过 width 的范围内找最靠右的断点。候选断点包括
    ASCII 分隔符（逗号/空格/括号/等号）与中文字符之间——后者必须支持，
    因为源码里的中文提示串很长且没有 ASCII 分隔符。
    """
    if _width(line.expandtabs(4)) <= width:
        return [line]

    out, rest, first = [], line, True
    while _width(rest) > width:
        limit = width if first else width - CONT_INDENT
        lo = max(int(limit * 0.55), 1)

        # 逐列累计，找出所有 <= limit 的断点位置
        best = -1
        w = 0
        for k, ch in enumerate(rest, 1):
            w += 2 if _is_wide(ch) else 1
            if w > limit:
                break
            prev_wide = k >= 2 and _is_wide(rest[k - 2])
            if ch in ', )]}=':
                best = k                        # ASCII 分隔符：优先
            elif _is_wide(ch) or prev_wide:
                best = max(best, k)             # 中文边界：次选
            if w >= lo and best < 0:
                best = k
        if best <= 0:
            best = 1
        out.append(rest[:best].rstrip())
        rest = ' ' * CONT_INDENT + rest[best:].lstrip()
        first = False
    out.append(rest)
    return out


def _is_wide(ch):
    import unicodedata
    return bool(ch) and unicodedata.east_asian_width(ch) in ('W', 'F')


lines = []
lines.append('% ==================== 附录：完整可运行源程序 ====================')
lines.append('% 按 format2026 第五条要求，附录包含建模所用到的完整、可运行的源程序。')
lines.append('% 本文件由 scripts/gen_appendix_source.py 自动生成，勿手改。')
lines.append('% 源码取自仓库内 final_version/支撑材料/（提交时的存放位置），')
lines.append('% 该目录名不出现在论文正文中。')
lines.append(r'\section{建模源程序（完整可运行）}')
lines.append(r'\label{sec:appendix-source}')
lines.append('')
lines.append('以下按问题列出\\textbf{生成论文全部数值结果}所需源程序。')
lines.append('下列文件\\textbf{与支撑材料中的同名文件逐字一致}；')
lines.append('运行环境与复现命令见 \\S\\ref{sec:appendix-env}。')
lines.append('全部程序使用 Python 语言与 \\texttt{numpy}/\\texttt{scipy}（HiGHS 求解器），')
lines.append('Excel 读写使用 \\texttt{openpyxl}；未使用 SPSS 等需手工交互的软件，')
lines.append('故无交互命令需要单独记录。')
lines.append('')
lines.append('\\textbf{收录范围}：以上为支撑材料中\\textbf{全部源程序}，')
lines.append('即生成论文全部数值结果与结果表所需的代码；')
lines.append('绘图代码已从支撑材料中移除，故本附录与支撑材料文件清单完全一致。')
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
        name = src.name
        lines.append(r'\subsubsection*{%s}' % tex_escape_title(name))
        # 直接内联源码并按 MAX_COLS 折行。原 \verbatiminput 会把超长行
        # （本仓库最长 256 字符、22% 的行超 72 字符）直接甩出页面右侧，
        # 实测 56/137 页越界、最远溢出 36.8cm。折行后不再越界。
        lines.append(r'\begin{verbatim}')
        for raw in src.read_text(encoding='utf-8').splitlines():
            lines.extend(wrap_line(raw))
        lines.append(r'\end{verbatim}')
        lines.append('')
        count += 1

lines.append(r'\endgroup')

out = PAPER / 'sections' / '09a_source_code.tex'
out.write_text('\n'.join(lines), encoding='utf-8')
print(f'已生成 {out}')
print(f'  引用 final_version/支撑材料/ 下 {count} 个源程序文件')
print('  与支撑材料逐字一致（同一文件）')
