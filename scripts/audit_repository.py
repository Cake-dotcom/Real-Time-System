"""Read-only repository inventory and preservation audit (Python standard library).

Writes reports only under results/repository_cleanup; never changes Git's index.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/repository_cleanup"
LOCAL={".git",".venv","venv","env","__pycache__",".pytest_cache",".mypy_cache",".ruff_cache"}


def git(*args, input=None):
    return subprocess.run(["git",*args],cwd=ROOT,input=input,capture_output=True,check=True).stdout


def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""): h.update(part)
    return h.hexdigest()


def audit(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    paths=[p for p in ROOT.rglob("*") if p.is_file()]
    sizes={p.relative_to(ROOT).as_posix():p.stat().st_size for p in paths}
    dirs=defaultdict(int)
    for name,size in sizes.items(): dirs[name.split('/')[0]]+=size
    tracked=[p.decode('utf-8') for p in git('ls-files','-z').split(b'\0') if p]
    candidates=[p.decode('utf-8') for p in git('ls-files','-z','--cached','--others','--exclude-standard').split(b'\0') if p]
    candidates=sorted(set(candidates))
    objects=git('rev-list','--objects','--all').decode().splitlines()
    object_names={x.split(' ',1)[0]:x.split(' ',1)[1] if ' ' in x else '' for x in objects}
    details=git('cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)',
                input=('\n'.join(object_names)+'\n').encode()).decode().splitlines()
    blobs=[dict(oid=a,path=object_names[a],bytes=int(c)) for a,b,c in (line.split() for line in details) if b=='blob']
    protected={name:digest(ROOT/name) for name in sizes
               if name.split('/')[0] in {'src','tests','data','models','results','scripts','docs'}
               and not set(Path(name).parts)&LOCAL and not name.startswith('results/repository_cleanup/')}
    # Candidate bytes, not credential values, are scanned. Test/demo literals need
    # human classification; this is a bounded heuristic, not a secret guarantee.
    patterns={"private_key":rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
              "github_token":rb'\bgh[pousr]_[A-Za-z0-9]{30,}',
              "aws_access_id":rb'\bAKIA[A-Z0-9]{16}\b',
              "openai_token":rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}'}
    findings=[]; personal=[]
    for name in candidates:
        p=ROOT/name
        if not p.is_file() or p.suffix.lower() not in {'.py','.md','.json','.txt','.toml','.yml','.yaml','.csv','.log'}: continue
        b=p.read_bytes()
        for kind,pat in patterns.items():
            if re.search(pat,b): findings.append(dict(path=name,kind=kind))
        if re.search(rb'[A-Za-z]:[\\/](?:Users[\\/]|Real time systems project)',b): personal.append(name)
    duplicates=defaultdict(list)
    for name,h in protected.items(): duplicates[h].append(name)
    result=dict(stage=stage,working_directory_bytes=sum(sizes.values()),top_directories=dict(sorted(dirs.items(),key=lambda x:-x[1])),
        file_count=len(sizes),tracked_working_files_bytes=sum(sizes.get(n,0) for n in tracked),tracked_file_count=len(tracked),
        intended_commit_bytes=sum(sizes.get(n,0) for n in candidates),intended_file_count=len(candidates),
        git_directory_bytes=dirs.get('.git',0),reachable_git_blob_bytes=sum(x['bytes'] for x in blobs),
        approximate_prepared_clone_upper_bytes=sum(sizes.get(n,0) for n in candidates)+dirs.get('.git',0)+sum(sizes.get(n,0) for n in candidates),
        clone_estimate_method='Conservative loose-object estimate: intended checkout + existing .git + one uncompressed copy of all intended files as new objects; no commit or history rewrite performed.',
        largest_files=[dict(path=n,bytes=s) for n,s in sorted(sizes.items(),key=lambda x:-x[1])[:25]],
        largest_history_blobs=sorted(blobs,key=lambda x:-x['bytes'])[:15],
        intended_files_over_100MiB=[dict(path=n,bytes=sizes[n]) for n in candidates if sizes.get(n,0)>100*1024**2],
        tracked_generated=[n for n in tracked if set(Path(n).parts)&(LOCAL- {'.git'})],
        secret_pattern_findings=findings,personal_path_files=personal,
        duplicate_groups=[v for v in duplicates.values() if len(v)>1],
        protected_sha256=protected,intended_files=candidates)
    if stage=='after' and (OUT/'before.json').exists():
        old=json.loads((OUT/'before.json').read_text())['protected_sha256']
        result['preservation_changes']=[n for n,h in old.items() if protected.get(n)!=h]
    (OUT/(stage+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('stage','working_directory_bytes','tracked_working_files_bytes','intended_commit_bytes','git_directory_bytes','approximate_prepared_clone_upper_bytes','intended_files_over_100MiB','secret_pattern_findings')},indent=2))
    if 'preservation_changes' in result: print('Preservation changes:',result['preservation_changes'])


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('stage',choices=['before','after']); audit(p.parse_args().stage)
