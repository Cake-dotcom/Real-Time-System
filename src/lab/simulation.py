"""Security-gated recurring workload orchestration using the existing EDF engine."""
from copy import deepcopy
import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import time
from src.lab.config import validate
from src.lab.security import SecurityRuntime
from src.scheduler.dynamic_risk import RiskEvent
from src.scheduler.security_costs import default_registry, Mechanism
from src.scheduler.experiments import run_algorithm, digest, estimate, ALGORITHMS


def run(raw,algorithm=None):
    started=time.perf_counter_ns(); config=validate(raw)
    algorithm=algorithm or raw.get("algorithm","RA-LP-EDF")
    if algorithm not in ALGORITHMS: raise ValueError("Unsupported algorithm")
    security=SecurityRuntime(config)
    events=[]
    external=list(config.events)
    for event in config.events:
        if event["type"].startswith("risk_"):
            events.extend(RiskEvent(event["time"],t,event["value"]) for t in event["targets"])
            if event["duration"] and event["time"]+event["duration"]<=config.horizon:
                events.extend(RiskEvent(event["time"]+event["duration"],t,
                    next(task.exposure for task in config.tasks if task.task_id==t)) for t in event["targets"])
                external.append({**event,"time":event["time"]+event["duration"],"type":"risk_recovery",
                    "event_id":event["event_id"]+":end","description":"Configured duration ended; return to initial exposure"})
    registry=default_registry()
    registry["mandatory"]=Mechanism("mandatory",3,0,0,0,0,0,0,.9,
        provenance="Existing mandatory authentication/validation configured costs, interpreted in ms")
    trace=run_algorithm(config.tasks,events,algorithm,horizon=config.horizon,policy=config.policy,registry=registry,
        checkpoint=config.original["checkpoint"]*config.factor,
        release_hook=security.release,completion_hook=security.complete,
        external_events=external,event_hook=security.event,capture_snapshots=True)
    monitoring=security.finish(trace)
    if trace.get("static_analysis") is not None:
        trace["static_analysis"].update(integrated_certificate=False,
            integrated_scope="Template-only analysis excludes release-time mandatory validation budgets; not a certificate for this trace")
    messages=monitoring["messages"]; jobs=trace["jobs"]
    rejected=sum(not m["gate_eligible"] for m in messages)
    trace["metrics"].update(pre_scheduler_rejections=rejected,
        admission_rejections=sum(j["state"]=="rejected" and security.audit[j["job_id"]]["gate_eligible"] for j in jobs),
        executed_jobs=sum(j["start"] is not None for j in jobs),
        trusted_history_commits=sum(m["history_committed"] for m in messages),
        successful_mac_verifications=sum(m.get("authentication")=="passed" for m in messages),
        critical_deadline_misses_by_class={c:sum(j["state"]=="deadline_missed" and j["criticality"]==c for j in jobs)
                                         for c in ("critical","high","normal","low")})
    # Admission outcomes can differ by algorithm; source releases and events cannot.
    identity={"tasks":[asdict(t) for t in config.tasks],"events":list(config.events),"seed":raw.get("seed",11),
              "horizon":config.horizon,"health_backend":raw.get("health_backend","RF"),"details":config.details,
              "auth_cost_ms":raw.get("auth_cost_ms",1)}
    return {"configuration":deepcopy(raw),"workload_id":digest(identity),"algorithm":algorithm,"internal_unit":"ms",
        "display_unit":raw.get("time_unit","s"),"trace":trace,"security":monitoring,
        "policy":asdict(config.policy),"mechanisms":{k:asdict(v) for k,v in registry.items()},
        "health_runtime":"Run-local RF inference uses one worker; model weights unchanged. GRU retains its configured runtime.",
        "wall_ms":(time.perf_counter_ns()-started)/1e6,
        "limitations":["Configured costs are not measured WCET", "Finite released-job feasibility is not an infinite-arrival guarantee",
            "Real authentication and RF/GRU gates; anomalous/unavailable health conditions are labelled scenario evidence injection",
            "Static analysis excludes release-time validation budgets and cannot certify this integrated trace",
            "Comparisons share releases/events but trusted histories and eligibility may diverge after different completion outcomes"],
        "source_hashes":{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ("src/lab","src/scheduler","src/security") for p in Path(folder).glob("*.py")}}


def compare(raw,algorithms=ALGORITHMS):
    results=[run(raw,a) for a in algorithms]
    if len({r["workload_id"] for r in results})>1: raise RuntimeError("Comparison workload identity mismatch")
    return results


def csv_bytes(rows):
    if not rows: return b""
    columns=list(dict.fromkeys(key for row in rows for key in row))
    out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=columns); writer.writeheader()
    for row in rows:
        writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list,tuple)) else v for k,v in row.items()})
    return out.getvalue().encode("utf-8")


def export_json(result): return json.dumps(result,indent=2,allow_nan=False).encode("utf-8")


def playback(result,index):
    trace=result["trace"]; snapshots=trace["snapshots"]
    if not snapshots: return {"time":0,"jobs":[],"ready":[],"running":None,"safe_state_events":0,"next_event":None}
    snapshot=deepcopy(snapshots[max(0,min(index,len(snapshots)-1))])
    snapshot["next_event"]=next((e for e in trace["events"] if e["time"]>snapshot["time"]),None)
    return snapshot
