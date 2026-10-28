"""Paired optimization benchmark. Run baseline BEFORE editing the engine."""
import argparse
import cProfile
import gzip
import hashlib
import json
import platform
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.scheduler.experiments import workload, run_algorithm

BASE = ("RA-LP-EDF", "Standard-EDF", "Static-Sec-EDF", "MPS-LP-EDF-structural")
NEW = ("RA-LP-EDF-Admission", "RA-LP-EDF-Preemption", "RA-LP-EDF-Optimized")


def execute(item):
    config, algorithms = item
    tasks, events = workload(**config)
    source = {"tasks": [asdict(t) for t in tasks], "events": [asdict(e) for e in events]}
    identity = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    traces = {a: run_algorithm(tasks, events, a, horizon=config["horizon"]) for a in algorithms}
    return dict(config=config, workload_id=identity, source=source, traces=traces)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["baseline", "optimized"])
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seeds", type=int, default=20)
    args = p.parse_args()
    out = ROOT / "results" / "optimization" / args.stage
    out.mkdir(parents=True, exist_ok=True)
    if (out / "runs.jsonl.gz").exists():
        raise SystemExit("Results already exist; preserve them or explicitly move the directory before rerunning.")
    files = sorted(list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")))
    hashes = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    with zipfile.ZipFile(out / "source.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in files + [Path(__file__)]: z.write(f, f.relative_to(ROOT))
    metadata = dict(stage=args.stage, source_sha256=hashes, python=sys.version,
                    platform=platform.platform(), workers=args.workers, seeds=list(range(101, 101+args.seeds)),
                    git_head=subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                    policy="Default Policy; TTL=horizon+maximum relative deadline+1; registry scale=1; EDF checkpoint=1",
                    runtime="Concurrent Python wall latency, not simulated WCET; all costs are configured estimates.")
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2))
    scenarios = [("S1-low", .5), ("S1-low", .85), ("S2-high", .85), ("S4-spike", .85), ("S7-overload", .95)]
    configs = [dict(n=n, utilization=u, seed=s, scenario=sc, horizon=200)
               for s in metadata["seeds"] for n in (4, 12) for sc,u in scenarios]
    algorithms = BASE if args.stage == "baseline" else ("RA-LP-EDF",) + NEW
    started = time.perf_counter()
    with gzip.open(out / "runs.jsonl.gz", "wt", encoding="utf-8") as f, ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, result in enumerate(pool.map(execute, [(c, algorithms) for c in configs]), 1):
            f.write(json.dumps(result) + "\n")
            if i % 10 == 0: print(f"{i}/{len(configs)} configurations saved", flush=True)
    tasks, events = workload(n=12, utilization=.85, seed=101, scenario="S4-spike", horizon=200)
    profiler = cProfile.Profile()
    profiler.runcall(run_algorithm, tasks, events, algorithms[-1], horizon=200)
    profiler.dump_stats(str(out / "scheduler.prof"))
    metadata.update(configurations=len(configs), runs=len(configs)*len(algorithms), elapsed_seconds=time.perf_counter()-started)
    metadata["source_unchanged"] = all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({k:metadata[k] for k in ("runs", "elapsed_seconds", "source_unchanged")}))


if __name__ == "__main__": main()
