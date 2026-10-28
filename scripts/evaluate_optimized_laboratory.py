"""Authenticated end-to-end optimization evidence and separate wall profiling."""
import cProfile
import gzip
import json
import pstats
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.lab.config import preset, PRESETS
from src.lab.simulation import run
from src.scheduler.experiments import workload,run_algorithm
from src.scheduler.model import Task,Phase
from src.scheduler.dynamic_risk import RiskEvent


def main():
    out=ROOT/"results"/"optimization"/"laboratory"; out.mkdir(parents=True,exist_ok=True)
    summary=[]
    with gzip.open(out/"runs.jsonl.gz","wt",encoding="utf-8") as f:
        configs=[(name,preset(name)) for name in PRESETS]
        for name,raw in configs:
            for mode in ("RA-LP-EDF","RA-LP-EDF-Admission","RA-LP-EDF-Preemption","RA-LP-EDF-Optimized"):
                result=run(raw,mode); trace=result["trace"]
                for a in result["security"]["messages"]:
                    j=next(j for j in trace["jobs"] if j["job_id"]==a["job_id"])
                    if not a["gate_eligible"]:
                        assert not j["admitted"] and j["start"] is None and not a["history_committed"]
                    if a["history_committed"]: assert j["state"]=="completed" and j["finish"]<=j["deadline"]+1e-8
                assert trace["metrics"]["security_compliance"] in (None,1.)
                assert trace["metrics"]["reservation_violations"]==0
                assert abs(sum(sum(j["costs"].values()) for j in trace["jobs"])-sum(t["end"]-t["start"] for t in trace["timeline"] if t["job"]))<1e-6
                f.write(json.dumps(dict(preset=name,result=result))+"\n")
                summary.append(dict(preset=name,algorithm=mode,workload_id=result["workload_id"],**trace["metrics"]))
            print(name,"verified",flush=True)
    (out/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    tasks=[Task("critical",(Phase("p",1,quantum=1),),20,5,kind="oneshot",safety_critical=True)]
    events=[RiskEvent(.1,"critical",1)]
    tradeoff={mode:run_algorithm(tasks,events,mode,horizon=20) for mode in ("RA-LP-EDF","RA-LP-EDF-Optimized")}
    (out/"unexpected_spike_tradeoff.json").write_text(json.dumps(tradeoff,indent=2),encoding="utf-8")
    # Warm RF loading precedes profile so inference and scheduler costs are visible.
    for mode in ("RA-LP-EDF","RA-LP-EDF-Optimized"):
        profiler=cProfile.Profile(); profiler.runcall(run,preset(),mode)
        profiler.dump_stats(str(out/(mode+"-full.prof")))
        tasks,events=workload(n=12,utilization=.85,seed=101,scenario="S4-spike",horizon=200)
        profiler=cProfile.Profile(); profiler.runcall(run_algorithm,tasks,events,mode,horizon=200)
        profiler.dump_stats(str(out/(mode+"-scheduler.prof")))
    with (out/"profiles.txt").open("w",encoding="utf-8") as f:
        for path in out.glob("*.prof"):
            f.write("\n"+path.name+"\n")
            pstats.Stats(str(path),stream=f).strip_dirs().sort_stats("cumtime").print_stats(18)
    print(len(summary),"authenticated runs verified",flush=True)


if __name__=="__main__": main()
