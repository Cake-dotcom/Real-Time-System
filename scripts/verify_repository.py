"""Packaging smoke checks; write only new cleanup evidence, never research results."""
import ast
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/"results/repository_cleanup"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={}
    files=[p for folder in ('src','tests','scripts') for p in (ROOT/folder).rglob('*.py')]
    for p in files: ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p.relative_to(ROOT)))
    report['syntax_files']=len(files)
    links=re.findall(r'\]\(([^)]+)\)',(ROOT/'README.md').read_text(encoding='utf-8-sig'))
    missing=[x for x in links if not x.startswith(('http:','https:','#')) and not (ROOT/x.split('#')[0]).exists()]
    assert not missing,missing
    report['readme_local_links']='all resolve'
    import joblib
    import numpy as np
    import pandas as pd
    from src.ml.gru_sensor_model import GRUPredictor
    from src.ml.skab_dataset import iter_windows
    from src.scheduler.experiments import workload,run_algorithm,ALGORITHMS
    from src.lab.config import preset
    from src.lab.simulation import compare
    bundle=joblib.load(ROOT/'models/sensor_health_model.joblib')
    frame=pd.read_csv(ROOT/'data/raw/av_sensor_messages.csv')
    report['rf_prediction']=str(bundle['model'].predict(frame[bundle['features']].head(1))[0])
    predictor=GRUPredictor()
    x,_,_=next(iter_windows(split='test'))
    result=predictor.predict(x[-predictor.length:]*predictor.scale+predictor.mean)
    assert np.isfinite(result['anomaly_score'])
    report['gru_prediction']=result['prediction']
    report['gru_weight_checksum']='validated by GRUPredictor'
    report['scheduler_comparisons']=[]
    tasks,events=workload(n=4,seed=101,scenario='S4-spike',horizon=200)
    for mode in ALGORITHMS:
        t=run_algorithm(tasks,events,mode,horizon=200)
        assert t['metrics']['security_compliance'] in (None,1.)
        assert all(j['finish']<=j['deadline']+1e-8 for j in t['jobs'] if j['state']=='completed')
        report['scheduler_comparisons'].append({'algorithm':mode,'completed':t['metrics']['completed_jobs']})
    raw=preset();raw['horizon']=1.
    compared=compare(raw,('RA-LP-EDF','RA-LP-EDF-Optimized'))
    assert len({r['workload_id'] for r in compared})==1
    assert all(r['trace']['metrics']['completed_jobs']==4 for r in compared)
    report['authenticated_comparison']='same workload, both modes complete all four verified messages'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    with (OUT/'streamlit-startup.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-m','streamlit','run','src/dashboard/app.py',
            '--server.headless','true','--server.address','127.0.0.1','--server.port',str(port),
            '--browser.gatherUsageStats','false'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            for _ in range(40):
                if process.poll() is not None: raise RuntimeError('Streamlit exited before healthy')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1) as response:
                        assert response.status==200
                        report['dashboard_startup']='localhost health HTTP 200; app execution separately covered by pytest AppTest'
                        break
                except OSError: time.sleep(.25)
            else: raise RuntimeError('Streamlit health timeout')
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
    (OUT/'smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
