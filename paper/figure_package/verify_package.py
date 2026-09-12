"""Read-only verification of generated plots, source mappings, and key derived values."""
from pathlib import Path
import hashlib
import json
import re

import numpy as np
import pandas as pd
import pymupdf
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def equal(a, b):
    np.testing.assert_allclose(a, b, rtol=1e-8, atol=1e-5)


def main():
    m = json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))
    assert len(m['figures']) == 10
    assert digest(HERE/'build_figures.py') == m['builder_sha256']
    for p, expected in (m['source_sha256'] | m['shared_code_sha256']).items():
        assert digest(ROOT/p) == expected, f'Changed input: {p}'
    for p, expected in m['output_sha256'].items():
        assert digest(HERE/p) == expected, f'Changed output: {p}'
    for f in m['figures']:
        p = HERE/'figures'/f['id']
        with pymupdf.open(p.with_suffix('.pdf')) as d:
            assert len(d) == 1
            assert abs(d[0].rect.width*25.4/72-180) < .1
            assert len(d[0].get_text()) > 40
        with Image.open(p.with_suffix('.png')) as im:
            assert abs(im.width-180/25.4*320) < 2
            assert abs(im.info['dpi'][0]-320) < .1
    print('PASS: ten PDF/PNG pairs, 180 mm width, 320 DPI, source/output hashes')

    with np.load(ROOT/'question1/results/solution.npz') as d:
        baseline = np.maximum(d['load']-d['pv'], 0)
        v = d['price']*(d['g']-baseline)
        book = pd.read_csv(HERE/'data/02_q1_cost_bridge.csv').set_index('item').value_yuan
        equal(book['avoided'], np.minimum(v, 0).sum())
        equal(book['extra'], np.maximum(v, 0).sum())
        equal(book['baseline']+book['avoided']+book['extra'], book['optimized'])
        equal(book['optimized'], d['obj_lp'])
    daily = pd.read_csv(HERE/'data/03_q2_daily_savings.csv')
    equal(daily.saving_yuan.cumsum(), daily.cumulative_saving_yuan)
    equal(daily.loc[daily.date >= '2025-03-05', 'saving_yuan'], 0)
    eq = pd.read_csv(HERE/'data/07_q42_savings.csv')
    equal(eq.planned_saving_yuan+eq.emergency_saving_yuan, eq.total_saving_yuan)
    for label, question in [('q3', 'question3'), ('q43', 'question4/part3')]:
        c = pd.read_csv(ROOT/question/'results/comparison.csv').set_index('mode')
        c = c.loc[['B_aligned','only_0','at_0_6','at_0_6_12','all']]
        derived = pd.read_csv(HERE/'data/09_q43_increment_comparison.csv')
        equal(derived[label+'_saving_yuan'], -np.diff(c.total_cost_yuan))
    print('PASS: independent cash bridge, daily saving timeline, price-information and update deltas')

    a = pd.read_csv(ROOT/'question3/results/schedule_detail.csv').set_index(['date','slot'])
    b = pd.read_csv(ROOT/'question4/part3/results/schedule_detail.csv').set_index(['date','slot'])
    data = pd.read_csv(HERE/'data/10_q43_paired_differences.csv').set_index(['date','slot'])
    for field, scale in [('price_yuan_per_kwh',1), ('adjusted_kwh',6), ('energy_after_kwh',1)]:
        equal(data[field+'_difference'], (b.loc[data.index,field]-a.loc[data.index,field])*scale)
    assert len(data) == 576
    print('PASS: all 576 paired values in each heatmap panel')

    text = (HERE/'图注与正文.md').read_text(encoding='utf-8')
    assert text.count('**图注：**') == text.count('**正文描述：**') == 10
    for ref in re.findall(r'\]\(([^)]+)\)', text):
        assert (HERE/ref).is_file(), ref
    assert (HERE/'insert_figures.tex').read_text(encoding='utf-8').count('\\includegraphics') == 10
    with pymupdf.open(HERE/'figures/09_q43_incremental_comparison.pdf') as d:
        text = d[0].get_text()
        for label in ['11.14', '5.08', '87.71', '103.93', '12.20', '10.45']:
            assert label in text, label
    print('PASS: ten captions/paragraphs, valid links, LaTeX snippets, PDF numeric labels')
    preview = HERE/'图文预览.pdf'
    if preview.exists():
        with pymupdf.open(preview) as d:
            assert len(d) == 10, f'Preview has {len(d)} pages'
            for page in d:
                assert '正文描述' in page.get_text()
        print('PASS: ten-page compiled preview, each page contains body text')
    else:
        print('NOTE: compiled preview not present; individual figures verified')


if __name__ == '__main__':
    main()
