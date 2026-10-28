"""Seeded paired finite-trace evaluation; no inferred deployment WCETs."""
import argparse
from collections import defaultdict
from dataclasses import asdict, replace
import hashlib
import itertools
import json
from pathlib import Path
import random
import statistics
import sys
import platform
from concurrent.futures import ProcessPoolExecutor
from src.scheduler.model import Task, Phase
from src.scheduler.dynamic_risk import Policy, RiskEvent
from src.scheduler.security_costs import default_registry
from src.scheduler.feasibility import mps_analysis
from src.scheduler.ra_lp_edf import RALPEDF

ALGORITHMS=("Standard-EDF","Static-Sec-EDF","MPS-LP-EDF-structural","SAEDF-style","RA-LP-EDF","RA-LP-EDF-Admission","RA-LP-EDF-Preemption","RA-LP-EDF-Optimized")
SCENARIOS=("S1-low","S2-high","S3-gradual","S4-spike","S5-recovery","S6-multiple","S7-overload")


def workload(n=8, utilization=.5, seed=11, scenario="S1-low", horizon=400,
             phases=None, critical_fraction=.25, actual_factor=1, max_preemptions=100):
    if n<1 or utilization<=0 or scenario not in SCENARIOS: raise ValueError("Invalid workload")
    rng=random.Random(seed)
    weights=[rng.uniform(.5,1.5) for _ in range(n)]
    tasks=[]; events=[]
    for i,w in enumerate(weights):
        period=rng.choice([100,125,200]); count=phases or rng.randint(1,6)
        base=utilization*w/sum(weights)*period*(1.5 if scenario=="S7-overload" else 1)
        parts=[rng.uniform(.5,1.5) for _ in range(count)]
        phase_list=tuple(Phase(str(k),base*x/sum(parts),quantum=5) for k,x in enumerate(parts))
        deadline=period if i%2==0 else period*rng.uniform(.7,.95)
        exposure=.9 if scenario in {"S2-high","S5-recovery"} else .1
        kind="periodic" if i%3 else "sporadic"
        arrivals=[]; cursor=0
        while cursor<horizon:
            arrivals.append(cursor); cursor+=period*rng.uniform(1,1.25)
        tasks.append(Task(str(i),phase_list,period,deadline,kind=kind,
            arrivals=tuple(arrivals) if kind=="sporadic" else (),
            safety_critical=i<round(n*critical_fraction),exposure=exposure,
            actual_factor=actual_factor,max_preemptions=max_preemptions))
        changes={"S3-gradual":[(horizon*.25,.4),(horizon*.5,.65),(horizon*.75,.9)],
                 "S4-spike":[(horizon*.35,1)],"S5-recovery":[(horizon*.35,.1)],
                 "S6-multiple":[(horizon*.25,1),(horizon*.65,.1)]}.get(scenario,[])
        if scenario!="S4-spike" or i==0:
            events.extend(RiskEvent(t,str(i),r) for t,r in changes)
    return tasks,events


def run_algorithm(tasks, events, algorithm, *, horizon=400, policy=None, scale=1,
                  registry=None, checkpoint=1, **engine_options):
    registry=registry if registry is not None else default_registry(scale)
    # Constant-risk scenarios stay fresh through the final released job's
    # deadline, including the drain interval beyond the release horizon.
    base=policy or Policy(ttl=horizon+max([t.deadline for t in tasks]+[0])+1)
    analysis=None
    if algorithm in {"Standard-EDF","Static-Sec-EDF"}:
        # Conventional EDF approximated at 1-unit checkpoints, with real costs.
        tasks=[replace(t,phases=tuple(replace(p,quantum=checkpoint) for p in t.phases)) for t in tasks]
        base=replace(base,admission=False,reservations=False,overload=False)
    elif algorithm=="MPS-LP-EDF-structural":
        choices={(t.task_id,p.phase_id):"strong" for t in tasks for p in t.phases}
        analysis=mps_analysis(tasks,registry,choices)
        if analysis["status"]=="feasible":
            tasks=[replace(t,phases=tuple(replace(p,quantum=p.wcet/count)
                for p,count in zip(t.phases,analysis["counts"][t.task_id]))) for t in tasks]
        base=replace(base,reservations=False)
    trace=RALPEDF(tasks,events,policy=replace(base,mode=algorithm),registry=registry,horizon=horizon,**engine_options).run()
    trace["static_analysis"]=analysis
    return trace


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def estimate(values):
    values=[v for v in values if v is not None]
    if not values: return {"n":0,"mean":None,"std":None,"ci95_normal":None}
    mean=statistics.mean(values); std=statistics.stdev(values) if len(values)>1 else None
    half=1.96*std/len(values)**.5 if std is not None else None
    return {"n":len(values),"mean":mean,"std":std,"ci95_normal":[mean-half,mean+half] if half is not None else None}


def evaluate_configuration(config):
    sample=config.pop("save_trace")
    tasks,events=workload(**config)
    source={"tasks":[asdict(t) for t in tasks],"events":[asdict(e) for e in events]}
    config_id=digest(source); rows=[]; traces={}
    for algorithm in ALGORITHMS:
        trace=run_algorithm(tasks,events,algorithm)
        rows.append({**config,"config_id":config_id,"algorithm":algorithm,**trace["metrics"]})
        if sample: traces[algorithm]=trace
    return {**config,"id":config_id,**source},rows,traces


def evaluate(output, *, full=False, seeds=(11,22,33,44,55), workers=1):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path("src/scheduler").glob("*.py")}
    sizes=[4,8,12,16,20] if full else [4,8]
    utilizations=[.2,.5,.75,.95] if full else [.5,.95]
    rows=[]; configs=[]
    grid=[dict(scenario=scenario,n=n,utilization=u,seed=seed,
        save_trace=seed==seeds[0] and n==sizes[0] and u==utilizations[0])
        for scenario,n,u,seed in itertools.product(SCENARIOS,sizes,utilizations,seeds)]
    executor=ProcessPoolExecutor(max_workers=workers) if workers>1 else None
    try:
        evaluated=executor.map(evaluate_configuration,grid) if executor else map(evaluate_configuration,grid)
        for index,(config,measurements,traces) in enumerate(evaluated,1):
            configs.append(config); rows.extend(measurements)
            for algorithm,trace in traces.items():
                (output/f"trace_{config['scenario']}_{algorithm}.json").write_text(json.dumps(trace,indent=2),encoding="utf-8")
            if index%50==0: print(f"Evaluated {index}/{len(grid)} paired configurations",flush=True)
    finally:
        if executor: executor.shutdown()
    metrics=("released_on_time_ratio","critical_deadline_miss_ratio","security_overhead",
             "mean_residual_risk_while_executing","scheduler_wall_ms","preemptions","mechanism_switches",
             "rejection_ratio","ever_deferred_ratio","safe_state_events","simulated_cpu_utilization")
    grouped=defaultdict(list)
    for row in rows: grouped[(row["scenario"],row["n"],row["utilization"],row["algorithm"])].append(row)
    aggregates=[{"scenario":key[0],"n":key[1],"utilization":key[2],"algorithm":key[3],
        "metrics":{m:estimate([r[m] for r in values]) for m in metrics}} for key,values in grouped.items()]
    indexed={(r["config_id"],r["algorithm"]):r for r in rows}; paired=[]
    for scenario,n,u,algorithm in grouped:
        if algorithm=="RA-LP-EDF": continue
        comparisons=grouped[(scenario,n,u,algorithm)]
        paired.append({"scenario":scenario,"n":n,"utilization":u,"baseline":algorithm,
            "difference":"RA-LP-EDF minus baseline", "metrics":{m:estimate([
                indexed[(r["config_id"],"RA-LP-EDF")][m]-r[m] for r in comparisons
                if r[m] is not None and indexed[(r["config_id"],"RA-LP-EDF")][m] is not None]) for m in metrics}})
    # One-factor-at-a-time sensitivity and ablations on identical seeds.
    variants={"default":{},"no_dynamic":{"dynamic":False},"no_switch_awareness":{"switch_aware":False},
        "no_preemption":{"preemption":False},"no_admission":{"admission":False},
        "no_reservations":{"reservations":False},"no_overload":{"overload":False},
        "risk_weight_low":{"alpha":.2},"risk_weight_high":{"alpha":3},
        "cost_weight_high":{"beta":1},"switch_weight_high":{"gamma":3},
        "thresholds_low":{"low":.2,"high":.5},"thresholds_high":{"low":.5,"high":.85}}
    sensitivity=[]
    for seed in seeds:
        for label,changes in variants.items():
            tasks,events=workload(seed=seed,scenario="S6-multiple",utilization=.75)
            trace=run_algorithm(tasks,events,"RA-LP-EDF",policy=replace(Policy(ttl=601),**changes))
            sensitivity.append({"seed":seed,"variant":label,"policy_changes":changes,**trace["metrics"]})
        for label,changes,scale in [("cost_low",{},.25),("cost_high",{},3),
            ("one_phase",{"phases":1},1),("six_phases",{"phases":6},1),
            ("all_critical",{"critical_fraction":1},1),("no_critical",{"critical_fraction":0},1),
            ("wcet_overrun",{"actual_factor":1.1},1),("wcet_slack",{"actual_factor":.7},1),
            ("zero_preemptions",{"max_preemptions":0},1)]:
            tasks,events=workload(seed=seed,scenario="S6-multiple",utilization=.75,**changes)
            trace=run_algorithm(tasks,events,"RA-LP-EDF",scale=scale)
            sensitivity.append({"seed":seed,"variant":label,"workload_changes":changes,"cost_scale":scale,**trace["metrics"]})
    metadata={"python":sys.version,"platform":platform.platform(),"seeds":seeds,"full":full,
        "workers":workers,"wall_time_conditions":"Main grid measured with configured worker concurrency; sensitivity runs sequential. Wall latency is not a WCET.",
        "main_runs":len(rows),"sensitivity_runs":len(sensitivity),"horizon":400,
        "source_sha256":source_hashes,
        "cost_provenance":"configured synthetic simulation estimates; no measured crypto WCET",
        "utilization_definition":"base execution / period, excluding security and transition costs; S7 multiplies base by 1.5",
        "confidence_interval":"normal approximation across paired seeds per configuration; five repeats are exploratory"}
    for name,value in [("raw",rows),("workloads",configs),("aggregates",aggregates),("paired",paired),
                       ("sensitivity",sensitivity),("metadata",metadata)]:
        (output/f"{name}.json").write_text(json.dumps(value,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="results/scheduling")
    parser.add_argument("--full",action="store_true")
    parser.add_argument("--workers",type=int,default=1)
    args=parser.parse_args(); evaluate(args.output,full=args.full,workers=args.workers)

