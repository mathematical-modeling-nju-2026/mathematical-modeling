"""Redraw Q3/Q4-3 from saved results and copy the five figures used by the paper.

No optimization is run. Each plotting script runs in a separate interpreter;
the mapping below prevents identically named branch figures from being mixed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

PAPER = Path(__file__).resolve().parent
ROOT = PAPER.parent
BRANCHES = ('question3', 'question4/part3')
SOURCES = ('comparison.csv', 'schedule_detail.csv', 'forecast_diagnostics.csv')
FIGURES = {
    'q3_cost.pdf': ('question3', 'cost_comparison.pdf'),
    'q3_dispatch.pdf': ('question3', 'target_dispatch.pdf'),
    'q3_fusion.pdf': ('question3', 'forecast_fusion.pdf'),
    'q43_cost.pdf': ('question4/part3', 'cost_comparison.pdf'),
    'q43_dispatch.pdf': ('question4/part3', 'target_dispatch.pdf'),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inputs = {str((ROOT/branch/'results'/name).relative_to(ROOT).as_posix()):
              digest(ROOT/branch/'results'/name) for branch in BRANCHES for name in SOURCES}
    for branch in BRANCHES:
        subprocess.run([sys.executable, '-B', '-X', 'utf8',
                        str(ROOT/branch/'code/plot_q3.py')], cwd=PAPER, check=True)
    if any(digest(ROOT/path) != expected for path, expected in inputs.items()):
        raise RuntimeError('Input results changed while redrawing figures; no paper copies published.')

    # Cost and dispatch depend on different electricity prices in these branches.
    # Fusion diagnostics are allowed to match because the PV forecaster is shared.
    for name in ('cost_comparison.png', 'target_dispatch.png'):
        if digest(ROOT/'question3/results/figures'/name) == digest(ROOT/'question4/part3/results/figures'/name):
            raise RuntimeError(f'Unexpected duplicate Q3/Q4-3 figure: {name}')
    (PAPER/'figs').mkdir(exist_ok=True)
    copied = {}
    for target, (branch, name) in FIGURES.items():
        source = ROOT/branch/'results/figures'/name
        dest = PAPER/'figs'/target
        shutil.copy2(source, dest)
        if digest(source) != digest(dest):
            raise RuntimeError(f'Paper figure copy differs: {target}')
        copied[target] = dict(source=source.relative_to(ROOT).as_posix(), sha256=digest(dest))
    provenance = dict(input_sha256=inputs, figures=copied,
                      note='Q3/Q4-3 PV fusion diagnostics are shared; identical fusion curves are expected.')
    (PAPER/'figs/q3_figure_sources.json').write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Updated paper figures:', ', '.join(FIGURES))


if __name__ == '__main__':
    main()
