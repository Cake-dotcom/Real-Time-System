"""Repeated authenticated laboratory trials using the existing workload generator."""
from dataclasses import asdict
import itertools
import json
from src.scheduler.experiments import workload, estimate, SCENARIOS, ALGORITHMS
from src.lab.simulation import run


def generated_configuration(n,utilization,seed,scenario,horizon=4):
    tasks,events=workload(n,utilization,seed,scenario,horizon=400)
    scale=horizon/400  # Existing abstract time -> user seconds, once at boundary.
    rows=[]
    for task in tasks:
        rows.append(dict(task_id=task.task_id,sensor_id="SIM_"+task.task_id,sensor_type="generic",
            description="Seeded existing-generator workload",criticality="safety-critical" if task.protected else "medium",
            release=task.release*scale,execution=sum(p.wcet for p in task.phases)*scale,
            deadline=task.deadline*scale,period=task.period*scale,kind=task.kind,minimum_level=task.minimum_level,
            exposure=task.exposure,health="normal",message="valid",quantum=5*scale,max_preemptions=task.max_preemptions,
            arrivals=json.dumps([t*scale for t in task.arrivals]) if task.kind=="sporadic" else "",
            phases=json.dumps([dict(phase_id=p.phase_id,execution=p.wcet*scale,quantum=5*scale,
                                   minimum_level=p.minimum_level) for p in task.phases])))
    return dict(time_unit="s",horizon=horizon,seed=seed,algorithm="RA-LP-EDF",health_backend="RF",auth_cost_ms=1,
        checkpoint=5*scale,tasks=rows,policy={"ttl":horizon+5},
        events=[dict(event_id=f"E{i}",target=e.task_id,type="risk_spike",time=e.time*scale,duration=0,
                     value=e.exposure,description="Seeded scenario exposure update",repeat_every=0,job_number=0)
                for i,e in enumerate(events)])


def repeated(*,seeds=(11,22,33),counts=(4,),utilizations=(.75,),scenarios=("S4-spike",),
             algorithms=("Standard-EDF","Static-Sec-EDF","RA-LP-EDF"),horizon=4):
    if not all([seeds,counts,utilizations,scenarios,algorithms]): raise ValueError("Every experiment dimension needs a value")
    count=len(seeds)*len(counts)*len(utilizations)*len(scenarios)*len(algorithms)
    if count>60: raise ValueError("Interactive authenticated sweep is limited to 60 runs; use the existing standalone scheduler runner for larger grids")
    if len(set(seeds))!=len(seeds) or len(seeds)<2: raise ValueError("Use at least two distinct seeds")
    if any(s not in SCENARIOS for s in scenarios) or any(a not in ALGORITHMS for a in algorithms): raise ValueError("Unsupported scenario or algorithm")
    runs=[]; summaries=[]; paired=[]
    metrics=("released_on_time_ratio","deadline_miss_ratio","critical_deadline_miss_ratio","security_overhead",
             "mean_residual_risk_while_executing","security_compliance","scheduler_wall_ms","pre_scheduler_rejections")
    for n,u,scenario in itertools.product(counts,utilizations,scenarios):
        group=[]
        for seed in seeds:
            raw=generated_configuration(n,u,seed,scenario,horizon)
            for algorithm in algorithms:
                result=run(raw,algorithm)
                entry={"n":n,"utilization":u,"scenario":scenario,"seed":seed,"algorithm":algorithm,"result":result}
                runs.append(entry); group.append(entry)
        for algorithm in algorithms:
            rows=[r["result"]["trace"]["metrics"] for r in group if r["algorithm"]==algorithm]
            summaries.append({"n":n,"utilization":u,"scenario":scenario,"algorithm":algorithm,
                "metrics":{m:estimate([r[m] for r in rows]) for m in metrics}})
        reference=algorithms[0]
        for algorithm in algorithms[1:]:
            deltas={m:[] for m in metrics}
            for seed in seeds:
                first=next(r["result"] for r in group if r["seed"]==seed and r["algorithm"]==reference)
                other=next(r["result"] for r in group if r["seed"]==seed and r["algorithm"]==algorithm)
                if first["workload_id"]!=other["workload_id"]: raise RuntimeError("Unpaired workload")
                for m in metrics:
                    a,b=other["trace"]["metrics"][m],first["trace"]["metrics"][m]
                    if a is not None and b is not None: deltas[m].append(a-b)
            paired.append({"n":n,"utilization":u,"scenario":scenario,"algorithm":algorithm,"reference":reference,
                           "metrics":{m:estimate(values) for m,values in deltas.items()}})
    return {"runs":runs,"summary":summaries,"paired_differences":paired,
            "method":"Independent seeded source workloads; identical releases/events across algorithms per seed. Normal-approximation 95% CIs are exploratory, not a schedulability proof."}
