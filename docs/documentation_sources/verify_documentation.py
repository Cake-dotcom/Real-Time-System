"""Standard-library checks; no training, benchmark overwrite or runtime edits."""
import ast,csv,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'docs/documentation_validation'


def main():
    OUT.mkdir(exist_ok=True)
    initial=json.loads((OUT/'integrity_before.json').read_text())
    changed=[p for p,h in initial.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    syntax=list((ROOT/'src').rglob('*.py'))+list((ROOT/'tests').rglob('*.py'))
    for p in syntax:ast.parse(p.read_text(encoding='utf-8-sig'))
    readme=(ROOT/'README.md').read_text(encoding='utf-8-sig')
    links=re.findall(r'\]\(([^)]+)\)',readme)
    missing=[x for x in links if not x.startswith(('https://','http://','#')) and not (ROOT/x.split('#')[0]).exists()]
    assert not missing,missing
    headings={re.sub(r'[^a-z0-9 -]','',h.lower()).replace(' ','-') for h in re.findall(r'^## (.+)$',readme,re.M)}
    assert all(x[1:] in headings for x in links if x.startswith('#'))
    from src.scheduler.experiments import run_algorithm,ALGORITHMS,workload
    from src.scheduler.model import Task,Phase
    from src.security.risk_policy import select_validation_policy
    from src.security.auth_policy import choose_auth_action
    tasks=[Task('A',(Phase('p',2),),10,3,kind='oneshot'),Task('B',(Phase('p',1),),10,5,kind='oneshot')]
    trace=run_algorithm(tasks,[],'RA-LP-EDF-Optimized',horizon=10)
    assert [round(j['finish'],3) for j in trace['jobs']]==[2.081,3.142]
    (OUT/'illustrative_scheduler_trace.json').write_text(json.dumps(trace,indent=2))
    checks=[]
    for seed in (101,102,103):
        tasks,events=workload(n=4,seed=seed,scenario='S4-spike',horizon=200)
        for mode in ALGORITHMS:
            t=run_algorithm(tasks,events,mode,horizon=200)
            assert t['metrics']['security_compliance'] in (None,1.)
            assert all(j['finish']<=j['deadline']+1e-8 for j in t['jobs'] if j['state']=='completed')
            checks.append(dict(seed=seed,algorithm=mode,completed=t['metrics']['completed_jobs']))
    assert [select_validation_policy(r).validation_level for r in ('low','medium','high','critical','unknown')]==['standard','additional','enhanced','reject','unavailable']
    assert choose_auth_action('low',10)['action']=='temporary_block'
    rows=list(csv.DictReader((ROOT/'results/optimization/comparison.csv').open()))
    assert next(int(r['completed_jobs']) for r in rows if r['scenario']=='S7-overload/U=0.95' and r['algorithm']=='RA-LP-EDF-Optimized')==440
    ledger=(ROOT/'docs/documentation_sources/Command_Reference.md').read_text()
    modules=set(re.findall(r'-m (src\.[a-zA-Z0-9_.]+)',readme+ledger))
    assert all((ROOT/Path(*m.split('.'))).with_suffix('.py').exists() for m in modules)
    paths=set(re.findall(r'(?:scripts|docs/documentation_sources)/[a-zA-Z0-9_]+\.py',readme+ledger))
    assert all((ROOT/p).exists() for p in paths)
    report=dict(protected_files_unchanged=len(initial),syntax_files=len(syntax),readme_links='passed',
        illustrative_finishes=[2.081,3.142],scheduling_checks=checks,sensor_policy_names='passed',login_block_override='passed',
        saved_overload_count=440,verified_module_paths=sorted(modules),verified_script_paths=sorted(paths),
        full_suite='Not rerun: project environment removed by prior cleanup. Historical 278 passed in 57.09s retained.',
        setup='Source/CLI and prior environment evidence checked; no new clean dependency install or training.',
        external_links='Official SKAB, pinned data, NIST 800-30/800-82, MPS paper, SAEDF paper, PyTorch/scikit-learn opened during source research.')
    (OUT/'checks.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='scheduling_checks'},indent=2))


if __name__=='__main__':main()
