"""Generate the standalone Chinese PDF from its editable Markdown source.

Requirements: reportlab. Uses Windows Chinese fonts, embedded in the PDF.
Run: python 生成PDF.py [--overwrite]
"""

from pathlib import Path
import argparse
from html import escape
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = root / 'AI工具使用详情.md'
    output = root / 'AI工具使用详情.pdf'
    if output.exists() and not args.overwrite:
        raise SystemExit('PDF已存在；确认需要更新时请加 --overwrite。')

    pdfmetrics.registerFont(TTFont('ChineseBody', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('ChineseHead', 'C:/Windows/Fonts/simhei.ttf'))
    styles = {
        'body': ParagraphStyle('body', fontName='ChineseBody', fontSize=10.5,
                               leading=17.5, wordWrap='CJK', spaceAfter=8),
        'title': ParagraphStyle('title', fontName='ChineseHead', fontSize=20,
                                leading=28, alignment=TA_CENTER, spaceAfter=19),
        'h2': ParagraphStyle('h2', fontName='ChineseHead', fontSize=13,
                             leading=21, spaceBefore=8, spaceAfter=10, keepWithNext=True),
        'h3': ParagraphStyle('h3', fontName='ChineseHead', fontSize=11,
                             leading=18, spaceBefore=6, spaceAfter=8, keepWithNext=True),
    }

    def page(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFont('ChineseBody', 8)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawString(23 * mm, height - 16 * mm, 'AI工具使用详情')
        canvas.setStrokeColor(colors.HexColor('#CCCCCC'))
        canvas.line(23 * mm, height - 19 * mm, width - 23 * mm, height - 19 * mm)
        canvas.drawCentredString(width / 2, 14 * mm, f'第 {doc.page} 页')
        canvas.restoreState()

    story = []
    for block in re.split(r'\n\s*\n', source.read_text(encoding='utf-8').strip()):
        block = block.strip()
        if block == '<!-- pagebreak -->':
            story.append(PageBreak())
            continue
        key = 'body'
        for prefix, candidate in [('### ', 'h3'), ('## ', 'h2'), ('# ', 'title')]:
            if block.startswith(prefix):
                key, block = candidate, block[len(prefix):]
                break
        story.append(Paragraph(escape(block).replace('\n', '<br/>'), styles[key]))
    doc = SimpleDocTemplate(str(output), pagesize=A4,
                            rightMargin=23 * mm, leftMargin=23 * mm,
                            topMargin=25 * mm, bottomMargin=22 * mm,
                            title='AI工具使用详情', author='',
                            subject='参赛队AI工具使用场景、交互示例及核验记录')
    doc.build(story, onFirstPage=page, onLaterPages=page)
    print(output)


if __name__ == '__main__':
    main()
