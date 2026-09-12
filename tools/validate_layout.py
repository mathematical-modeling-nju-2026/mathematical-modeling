"""Check relocation integrity and inputs without solving or overwriting model results.

Run with the final-scheme requirements installed. Import each scheme in a fresh
process so the two intentionally distinct q3_model modules cannot shadow each
other. Reports describe migration checks, not a new full numerical reproduction.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SCHEMES = ('question1', 'question2', 'question3', 'question4/part2', 'question4/part3')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '.venv', '__pycache__')]
        for name in names:
            yield Path(directory)/name


def active(path):
    rel = path.relative_to(ROOT).as_posix()
    return (rel.startswith(('question1/', 'question2/', 'question3/', 'question4/', 'common/', 'data/'))
            and '/research/' not in rel)


def run_python(source):
    # An unrelated working directory proves no repository-CWD assumption is used.
    with tempfile.TemporaryDirectory(prefix='model-layout-') as cwd:
        proc = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', source],
                              cwd=cwd, capture_output=True, text=True, encoding='utf-8', timeout=180)
    return dict(pass_check=proc.returncode == 0, stdout=proc.stdout.strip(), stderr=proc.stderr.strip())


def main():
    report = dict(scope='Relocation integrity, syntax, imports, input reading, existing result consistency; no optimization rerun.',
                  python=sys.version)
    manifest = json.loads((ROOT/'docs/migration_manifest.json').read_text(encoding='utf-8'))
    missing, changed, preserved = [], [], []
    for row in manifest['files']:
        p = ROOT/row['new']
        if not p.is_file(): missing.append(row['new'])
        elif sha(p) != row['sha256']: changed.append(row['new'])
        else: preserved.append(row['new'])
    edited_code_or_docs=[p for p in changed if Path(p).suffix in ('.py','.md')]
    regenerated_or_edited_outputs=[p for p in changed if Path(p).suffix not in ('.py','.md')]
    changed_inputs=[p for p in changed if p.startswith('data/')]
    report['integrity'] = dict(total=len(manifest['files']), byte_identical=len(preserved), missing=missing,
                               edited_code_or_docs=edited_code_or_docs,
                               regenerated_or_edited_outputs=regenerated_or_edited_outputs,
                               changed_inputs=changed_inputs,
                               pass_check=not missing and not changed_inputs)
    report['original_results_overwritten']=any('/results/' in f'/{p}' for p in regenerated_or_edited_outputs)
    all_files = list(files())
    syntax_errors, absolute_refs, old_refs, broken_links, io_references = [], [], [], [], []
    py_count = md_count = 0
    for p in all_files:
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix not in ('.py', '.md'): continue
        s = p.read_text(encoding='utf-8-sig')
        if p.suffix == '.py':
            py_count += 1
            try:
                tree = ast.parse(s, filename=rel)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = ast.unparse(node.func)
                        if re.search(r'(^|\.)(open|read_csv|read_excel|load|load_workbook|savefig|savez|savez_compressed|to_csv|to_excel|read_text|read_bytes|write_text|write_bytes)$', name):
                            io_references.append(dict(file=rel,line=node.lineno,call=ast.unparse(node),active=active(p)))
            except SyntaxError as e: syntax_errors.append(dict(file=rel,line=e.lineno,error=str(e),active=active(p)))
        else:
            md_count += 1
            clean = re.sub(r'```.*?```', '', s, flags=re.S)
            for m in re.finditer(r'(!?)\[[^\]\n]*\]\(([^\n)]+)\)', clean):
                target=m.group(2).split('#')[0].strip('<>')
                if not target or re.match(r'[a-zA-Z]+://|mailto:', target): continue
                dest=(p.parent/unquote(target)).resolve()
                if not dest.exists(): broken_links.append(dict(file=rel,target=target,image=bool(m.group(1)),active=active(p)))
        for i, line in enumerate(s.splitlines(), 1):
            if re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]',line): absolute_refs.append(dict(file=rel,line=i,text=line.strip(),active=active(p)))
            if re.search(r'C_yang|CShen|方案B_滚动窗口优化|方案B_问题4_第三问重模拟',line):
                old_refs.append(dict(file=rel,line=i,text=line.strip(),active=active(p)))
    report['repository_scan'] = dict(python_files=py_count, markdown_files=md_count, syntax_errors=syntax_errors,
                                      broken_links=broken_links, absolute_path_mentions=absolute_refs,
                                      old_directory_mentions=old_refs,file_io_references=io_references)
    imports={}
    for scheme in SCHEMES:
        code=ROOT/scheme/'code'
        modules=sorted(p.stem for p in code.glob('*.py'))
        source=f'''import sys, importlib, json
from pathlib import Path
sys.path.insert(0, {str(code)!r})
modules={modules!r}
paths={{}}
for name in modules:
    module=importlib.import_module(name)
    for key in ('ATT1','ATT2','TPL2','RAW','SOURCE','BASE_DIR','HERE','OUT','SKILL','ATTACHMENTS'):
        value=getattr(module,key,None)
        if isinstance(value,Path):
            assert value.exists(), (name,key,str(value))
            paths[name+'.'+key]=str(value)
print(json.dumps(dict(modules=modules,paths=paths),ensure_ascii=False))
'''
        imports[scheme]=run_python(source)
    report['imports_from_unrelated_cwd']=imports
    inputs={}
    for scheme in ('question3','question4/part3'):
        inputs[scheme]=run_python(f'''import sys,json
sys.path.insert(0,{str(ROOT/scheme/'code')!r})
from q3_data import load_data
d=load_data()
print(json.dumps({{k:list(v.shape) for k,v in d.items() if hasattr(v,'shape')}}))
''')
    inputs['question1_and_question2']=run_python(f'''import sys,json
sys.path.insert(0,{str(ROOT/'common/q2_base')!r})
import q2_data
a=q2_data.load_attachment1(); d,l,v=q2_data.load_attachment2(); labels=q2_data.template_labels()
assert len(a[0])==144 and l.shape==v.shape==(365,144) and len(labels)==144
sys.path.insert(0,{str(ROOT/'question1/code')!r})
import q1_model
b=q1_model.load_attachment1(q2_data.ATT1)
assert len(b[0])==144
print('Q1/Q2: attachment1=144, attachment2=365x144, template=144; read successfully')
''')
    inputs['question4/part2']=run_python(f'''import sys,json
sys.path.insert(0,{str(ROOT/'question4/part2/code')!r})
from q42_model import read_prices
d,p=read_prices(); assert p.shape==(365,144)
print('Q4-2: attachment4=365x144; read successfully')
''')
    report['input_reads']=inputs
    # Compare inputs formerly used by 4-3, when that optional local collection exists.
    original=ROOT/'CUMCM2026Problems/C题/附件'
    report['q43_original_input_comparison']={}
    for i in (1,2,3,4):
        p=original/f'附件{i}.xlsx'
        report['q43_original_input_comparison'][p.name]=(sha(p)==sha(ROOT/'data/附件'/p.name)) if p.exists() else 'original local copy unavailable'
    # Read and recompute totals from saved detail, without invoking any solver.
    import numpy as np
    import pandas as pd
    z=np.load(ROOT/'question1/results/solution.npz',allow_pickle=True)
    totals={'question1':dict(stored=float(z['obj_lp']),from_saved_dispatch=float(z['price']@z['g']))}
    for scheme in SCHEMES[1:]:
        out=ROOT/scheme/'results'; summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
        daily=pd.read_csv(out/'daily_summary.csv')
        totals[scheme]=dict(stored=summary['total_cost_yuan'],from_saved_daily=float(daily.total_cost_yuan.sum()),days=len(daily))
    for value in totals.values():
        value['difference']=abs(value['stored']-value.get('from_saved_daily',value.get('from_saved_dispatch')))
        value['pass_check']=value['difference']<1e-6
    report['saved_total_consistency']=totals
    q2_metadata=json.loads((ROOT/'question2/results/run_metadata.json').read_text(encoding='utf-8'))
    q2_summary=json.loads((ROOT/'question2/results/summary.json').read_text(encoding='utf-8'))
    report['question2_published_metadata']=dict(
        first_residual_matches=q2_metadata.get('first_residual')==q2_summary.get('first_residual_index'),
        variant_matches=q2_metadata.get('published_variant')==q2_summary.get('recommended_variant'),
        candidate_matches=q2_metadata.get('candidate',{}).get('name')==q2_summary.get('name'))
    report['question2_published_metadata']['pass_check']=all(
        report['question2_published_metadata'].values())
    report['migrated_fingerprints']={}
    for scheme in ('question2','question4/part2'):
        path=ROOT/scheme/'results/source_fingerprints.migrated.json'
        fingerprints=json.loads(path.read_text(encoding='utf-8'))
        report['migrated_fingerprints'][scheme]=all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in fingerprints.items())
    report['known_research_missing_inputs']=[str(p.relative_to(ROOT)) for p in
        (ROOT/'question3/research/experiments/_q3_greedy_result.npz',ROOT/'question3/research/experiments/_peer_fc.npz') if not p.exists()]
    report['active_pass']=(report['integrity']['pass_check'] and all(x['pass_check'] for x in imports.values())
        and all(x['pass_check'] for x in inputs.values()) and all(x['pass_check'] for x in totals.values())
        and not any(x['active'] for x in syntax_errors+broken_links)
        and all(report['migrated_fingerprints'].values())
        and report['question2_published_metadata']['pass_check']
        and not any(x is False for x in report['q43_original_input_comparison'].values()))
    (ROOT/'docs/layout_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(active_pass=report['active_pass'],integrity=report['integrity'],
                         import_status={k:v['pass_check'] for k,v in imports.items()},
                         input_status={k:v['pass_check'] for k,v in inputs.items()},
                         syntax_errors=syntax_errors, active_broken_links=[x for x in broken_links if x['active']],
                         saved_total_consistency=totals),ensure_ascii=False,indent=2))
    return 0 if report['active_pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
