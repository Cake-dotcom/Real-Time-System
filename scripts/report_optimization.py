"""Audit actual traces and report seed-paired improvements and regressions."""
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.scheduler.experiments import estimate
from src.scheduler.security_costs import default_registry,chunk_cost,total

ROOT = Path(__file__).resolve().parents[1] / "results" / "optimization"


def read(stage):
    with gzip.open(ROOT/stage/"runs.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main():
    baseline, optimized = read("baseline"), read("optimized")
    old = {r["workload_id"]:r for r in baseline}
    groups = defaultdict(list); misses=[]; regressions=[]; pairs=defaultdict(lambda:defaultdict(list))
    for r in optimized:
        b = old[r["workload_id"]]
        # The original mode must reproduce its saved pre-change behavioral trace.
        for key in ("jobs", "events", "timeline", "reservations", "risk_history"):
            assert b["traces"]["RA-LP-EDF"][key] == r["traces"]["RA-LP-EDF"][key], (r["config"], key)
        traces = {**b["traces"], **r["traces"]}
        config = r["config"]; scenario=f'{config["scenario"]}/U={config["utilization"]}'
        reference=traces["RA-LP-EDF"]["metrics"]
        for algorithm,t in traces.items():
            m=t["metrics"]; groups[(scenario,algorithm)].append(m)
            completed=[j for j in t["jobs"] if j["state"]=="completed"]
            assert len(completed)==m["completed_jobs"]
            assert all(j["admitted"] and j["finish"]<=j["deadline"]+1e-8 for j in completed)
            assert abs(sum(sum(j["costs"].values()) for j in t["jobs"])-sum(x["end"]-x["start"] for x in t["timeline"] if x["job"]))<1e-6
            assert all(x["end"]<=y["start"]+1e-8 for x,y in zip(t["timeline"],t["timeline"][1:]))
            assert m["security_compliance"] in (None,1.0)
            for j in t["jobs"]:
                if j["state"]!="completed":
                    reason=j["transitions"][-1]["reason"]
                    source=next(s for s in r["source"]["tasks"] if s["task_id"]==j["task_id"])
                    registry=default_registry()
                    lower=sum(min(total(chunk_cost(c,m,decision=.001)) for m in registry.values()
                              if m.name in phase["mechanisms"] and m.level>=max(phase["minimum_level"],source["minimum_level"]))
                              for phase in source["phases"] for c in [phase["wcet"]])
                    cause="base execution exceeds individual deadline" if j["configured_base"]>j["deadline"]-j["release"] else (
                        "minimum mandatory security costs exceed individual deadline" if lower>j["deadline"]-j["release"] else
                        "risk increase inside fixed interval (safe stop)" if "Risk upgrade" in reason else
                        "admission/demand bound or interference; inherent infeasibility NOT proved")
                    misses.append(dict(workload_id=r["workload_id"],algorithm=algorithm,seed=config["seed"],scenario=scenario,
                        job_id=j["job_id"],critical=j["critical"],state=j["state"],admitted=j["admitted"],cause=cause,final_reason=reason,
                        individual_minimum_cost=lower,
                        alternatives_completing_this_job=[a for a,x in traces.items() if any(k["job_id"]==j["job_id"] and k["state"]=="completed" for k in x["jobs"])],
                        noncritical_interference=sum(max(0,min(i["end"],j["deadline"])-max(i["start"],j["release"])) for i in t["timeline"]
                            if i["job"] and any(k["job_id"]==i["job"] and not k["critical"] for k in t["jobs"])),
                        evidence=[e for e in t["events"] if e["job"]==j["job_id"]]))
            if algorithm!="RA-LP-EDF":
                for key in ("released_on_time_ratio","critical_completed_jobs","completed_jobs","security_overhead","preemptions","scheduler_wall_ms"):
                    pairs[(scenario,algorithm,key)][config["seed"]].append(m[key]-reference[key])
                if m["critical_completed_jobs"]<reference["critical_completed_jobs"]:
                    regressions.append(dict(workload_id=r["workload_id"],config=config,algorithm=algorithm,
                        baseline_critical=reference["critical_completed_jobs"],candidate_critical=m["critical_completed_jobs"]))
    rows=[]
    for (scenario,algorithm),values in groups.items():
        row=dict(scenario=scenario,algorithm=algorithm,runs=len(values))
        for key in ("released_jobs","admitted_jobs","completed_jobs","critical_jobs","critical_completed_jobs","security_overhead","preemptions","safe_state_events","scheduler_wall_ms"):
            row[key]=sum(v[key] for v in values)
        row["on_time_ratio"]=row["completed_jobs"]/row["released_jobs"]
        row["critical_on_time_ratio"]=row["critical_completed_jobs"]/row["critical_jobs"]
        rows.append(row)
    for row in rows:
        ref=next(x for x in rows if x["scenario"]==row["scenario"] and x["algorithm"]=="RA-LP-EDF")
        for key in ("completed_jobs","critical_completed_jobs","security_overhead","preemptions","scheduler_wall_ms"):
            row[key+"_delta"]=row[key]-ref[key]
            row[key+"_percent_change"]=100*(row[key]-ref[key])/ref[key] if ref[key] else None
    with (ROOT/"comparison.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    paired=[dict(scenario=s,algorithm=a,metric=k,**estimate([sum(v)/len(v) for v in seeds.values()])) for (s,a,k),seeds in pairs.items()]
    (ROOT/"paired_statistics.json").write_text(json.dumps(paired,indent=2))
    (ROOT/"critical_regressions.json").write_text(json.dumps(regressions,indent=2))
    with gzip.open(ROOT/"critical_misses.jsonl.gz","wt",encoding="utf-8") as f:
        for miss in misses:
            if miss["critical"]: f.write(json.dumps(miss)+"\n")
    with gzip.open(ROOT/"all_misses.jsonl.gz","wt",encoding="utf-8") as f:
        for miss in misses: f.write(json.dumps(miss)+"\n")
    lines=["# Paired optimization results", "", "20 seeds × two sizes (4,12) per scenario. Horizon 200; unchanged workload generator. Full inputs, policy, source archives and traces accompany results.", "",
        "| Scenario | Algorithm | All on time | Critical on time | Security overhead | Preemptions | Scheduler ms |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f'| {r["scenario"]} | {r["algorithm"]} | {r["completed_jobs"]}/{r["released_jobs"]} | {r["critical_completed_jobs"]}/{r["critical_jobs"]} | {r["security_overhead"]:.2f} | {r["preemptions"]} | {r["scheduler_wall_ms"]:.1f} |')
    lines += ["",f"Critical regressions versus original RA: {len(regressions)} algorithm/workload pairs, listed explicitly in critical_regressions.json. Combined optimized mode: {sum(r['algorithm']=='RA-LP-EDF-Optimized' for r in regressions)} pairs.",
        "", "Paired statistics use each seed's mean across the two sizes (20 independent seed clusters), sample SD and approximate normal 95% intervals. These synthetic scenarios do not establish deployment guarantees. Runtime includes concurrent-process contention.",
        "", "Critical miss records retain exact per-job event evidence. A failed sufficient admission test alone is NOT proof of inherent infeasibility. Static EDF and MPS use their documented checkpoint transformations; adaptive modes use identical fixed points.",
        "", "Audit passed: saved original RA behavioral traces reproduced exactly; all reported completions meet deadlines; timeline is serial; charged costs conserve CPU time; executing protection complies with current policy."]
    (ROOT/"report.md").write_text("\n".join(lines),encoding="utf-8")
    print("Audited",len(optimized),"paired workloads; report:",ROOT/"report.md")


if __name__=="__main__": main()
