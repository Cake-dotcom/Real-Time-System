"""Validated user boundary. All scheduler durations are milliseconds."""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from src.scheduler.model import Task, Phase, number
from src.scheduler.dynamic_risk import Policy
from src.scheduler.experiments import ALGORITHMS

MESSAGE_CONDITIONS=("valid","tampered","replay","malformed")
HEALTH_CONDITIONS=("normal","faulty","anomalous","unavailable")
EVENT_TYPES=(*MESSAGE_CONDITIONS,"faulty","anomalous","unavailable","risk_spike","risk_recovery",
             "risk_unavailable","revoke_session","expire_session","reauthenticate")
CRITICALITIES={"safety-critical":"critical","high":"high","medium":"normal","low":"low"}


@dataclass
class Configuration:
    original: dict
    tasks: tuple
    details: dict
    events: tuple
    horizon: float
    policy: Policy
    factor: float


def finite(value,name,positive=False):
    if isinstance(value,str):
        try: value=float(value)
        except ValueError: raise ValueError(f"{name}: a finite number is required") from None
    return float(number(value,name,positive))


def integer(value,name,minimum=0):
    x=finite(value,name)
    if int(x)!=x or x<minimum: raise ValueError(f"{name}: integer ≥ {minimum} required")
    return int(x)


def parsed(value,name):
    if value is None or value=="": return []
    if isinstance(value,str):
        try: return json.loads(value)
        except ValueError: raise ValueError(f"{name}: valid JSON is required") from None
    return deepcopy(value)


def validate(raw):
    raw=deepcopy(raw)
    unit=raw.get("time_unit","s")
    if unit not in {"s","ms"}: raise ValueError("Time unit must be s or ms")
    factor=1000. if unit=="s" else 1.
    horizon=finite(raw.get("horizon",15),"Simulation horizon",True)*factor
    if horizon>3_600_000: raise ValueError("Interactive horizon is limited to one hour")
    raw["seed"]=integer(raw.get("seed",11),"Seed")
    if raw.get("algorithm","RA-LP-EDF") not in ALGORITHMS: raise ValueError("Unsupported algorithm")
    if raw.get("health_backend","RF") not in {"RF","GRU"}: raise ValueError("Select RF or GRU")
    raw["auth_cost_ms"]=finite(raw.get("auth_cost_ms",1),"Authentication cost")
    raw["checkpoint"]=finite(raw.get("checkpoint",.05 if unit=="s" else 50),"Baseline checkpoint",True)
    checkpoint=raw["checkpoint"]*factor
    tasks=[]; details={}; sensors={}
    rows=raw.get("tasks",[])
    if len(rows)>32: raise ValueError("Interactive laboratory supports at most 32 task templates")
    for row in rows:
        name=row.get("task_id")
        if not isinstance(name,str) or not name.strip() or name in details: raise ValueError("Each task needs a unique nonempty Task ID")
        source=row.get("sensor_id")
        if not isinstance(source,str) or not source.strip(): raise ValueError(f"{name}: Sensor ID is required")
        criticality=row.get("criticality","medium")
        if criticality not in CRITICALITIES: raise ValueError(f"{name}: Invalid criticality")
        if row.get("message","valid") not in MESSAGE_CONDITIONS: raise ValueError(f"{name}: Invalid message condition")
        if row.get("health","normal") not in HEALTH_CONDITIONS: raise ValueError(f"{name}: Invalid health condition")
        kind=row.get("kind","oneshot")
        execution=finite(row.get("execution"),f"{name} execution",True)*factor
        deadline=finite(row.get("deadline"),f"{name} relative deadline",True)*factor
        period=deadline if kind=="oneshot" and row.get("period") in (None,0,"") else finite(row.get("period"),f"{name} period",True)*factor
        release=finite(row.get("release",0),f"{name} release")*factor
        level=integer(row.get("minimum_level",1),f"{name} minimum security",1)
        exposure=row.get("exposure",.1)
        if exposure=="" or exposure is None: exposure=None
        else: exposure=finite(exposure,f"{name} exposure")
        quantum=finite(row.get("quantum",.05 if unit=="s" else 50),f"{name} quantum",True)*factor
        phase_rows=parsed(row.get("phases",""),f"{name} phases")
        phases=[]
        for i,p in enumerate(phase_rows):
            phases.append(Phase(str(p.get("phase_id",i+1)),finite(p.get("execution"),f"{name} phase execution",True)*factor,
                tuple(p.get("mechanisms",["light","medium","strong"])),integer(p.get("minimum_level",level),"Phase minimum",1),
                finite(p.get("quantum",quantum/factor),"Phase quantum",True)*factor,p.get("preemptible",True)))
        if not phases: phases=[Phase("application",execution,minimum_level=level,quantum=quantum)]
        if not math.isclose(sum(p.wcet for p in phases),execution,abs_tol=1e-6):
            raise ValueError(f"{name}: phase execution sum must equal the configured execution budget")
        if any(m not in {"light","medium","strong"} for p in phases for m in p.mechanisms): raise ValueError(f"{name}: Unknown mechanism")
        arrivals=tuple(finite(t,"Sporadic arrival")*factor for t in parsed(row.get("arrivals",""),f"{name} arrivals"))
        task=Task(name,tuple(phases),period,deadline,release,kind,arrivals,CRITICALITIES[criticality],
            criticality=="safety-critical",level,exposure,sensor_type=str(row.get("sensor_type","generic")),
            max_preemptions=integer(row.get("max_preemptions",100),"Preemption cap"))
        if kind=="periodic" and (horizon-release)/period>200:
            raise ValueError(f"{name}: more than 200 releases; increase period or shorten horizon")
        count=(max(0,math.ceil((horizon-release)/period-1e-9)) if kind=="periodic" else
               sum(t<horizon for t in arrivals) if kind=="sporadic" else int(release<horizon))
        if count>200: raise ValueError(f"{name}: more than 200 releases; increase period or shorten horizon")
        if any(p.preemptible and p.quantum and p.wcet/p.quantum>20000 for p in phases):
            raise ValueError(f"{name}: too many fixed intervals; increase quantum")
        if any(p.wcet/checkpoint>20000 for p in phases):
            raise ValueError(f"{name}: too many baseline intervals; increase checkpoint")
        chunks=sum(max(1,math.ceil(p.wcet/p.quantum-1e-9)) if p.preemptible and p.quantum else 1 for p in phases)
        if count*chunks>20000: raise ValueError(f"{name}: too many fixed intervals; increase quantum")
        tasks.append(task); details[name]=row
        metadata=(task.sensor_type,criticality)
        if source in sensors and sensors[source]!=metadata: raise ValueError(f"{source}: shared sensor templates must agree on type and criticality")
        sensors[source]=metadata
    if sum(len(t.releases(horizon)) for t in tasks)>500: raise ValueError("Interactive run limited to 500 jobs")
    if sum(len(t.releases(horizon))*sum(max(1,math.ceil(p.wcet/p.quantum-1e-9)) if p.preemptible and p.quantum else 1 for p in t.phases) for t in tasks)>20000:
        raise ValueError("Too many fixed intervals; increase quantum or reduce workload")
    if sum(len(t.releases(horizon))*sum(math.ceil(p.wcet/checkpoint) for p in t.phases) for t in tasks)>20000:
        raise ValueError("Too many baseline intervals; increase the EDF checkpoint or reduce workload")
    events=[]; identifiers=set()
    for event in raw.get("events",[]):
        event=deepcopy(event); eid=event.get("event_id")
        if not isinstance(eid,str) or not eid or eid in identifiers: raise ValueError("Each event needs a unique Event ID")
        identifiers.add(eid)
        if event.get("type") not in EVENT_TYPES: raise ValueError(f"{eid}: Invalid event type")
        targets=[t.task_id for t in tasks if event.get("target") in {t.task_id,details[t.task_id]["sensor_id"]}]
        if not targets: raise ValueError(f"{eid}: target must name a configured task or sensor")
        at=finite(event.get("time",0),f"{eid} time")*factor
        duration=finite(event.get("duration",0),f"{eid} duration")*factor
        repeat=finite(event.get("repeat_every",0),f"{eid} repeat interval")*factor
        index=integer(event.get("job_number",0),f"{eid} job number")
        if index:
            if len(targets)!=1: raise ValueError(f"{eid}: job trigger requires one task target")
            releases=next(t for t in tasks if t.task_id==targets[0]).releases(horizon)
            if index>len(releases): raise ValueError(f"{eid}: job number is outside this horizon")
            at=releases[index-1]
            if repeat: raise ValueError(f"{eid}: choose a job trigger or repetition, not both")
        value=event.get("value",.9)
        if event["type"].startswith("risk_"):
            value=None if event["type"]=="risk_unavailable" else finite(value,f"{eid} risk value")
            if value is not None and value>1: raise ValueError(f"{eid}: risk must be in [0,1]")
        if at>=horizon: raise ValueError(f"{eid}: event must occur before the release horizon")
        occurrences=1 if not repeat else math.ceil((horizon-at)/repeat)
        if occurrences>500: raise ValueError(f"{eid}: too many repetitions")
        for k in range(occurrences):
            events.append({**event,"event_id":f"{eid}:{k}","time":at+k*repeat,"duration":duration,
                           "targets":targets,"value":value,"job_number":index})
    if len(events)>1000: raise ValueError("Interactive run limited to 1000 events")
    policy_values=raw.get("policy",{})
    policy=Policy(**{k:v for k,v in policy_values.items() if k not in {"dwell","ttl","decision_cost"}},
        dwell=finite(policy_values.get("dwell",.5 if unit=="s" else 500),"Dwell")*factor,
        ttl=finite(policy_values.get("ttl",30 if unit=="s" else 30000),"Risk freshness",True)*factor,
        decision_cost=finite(policy_values.get("decision_cost",.001),"Decision cost (ms)"))
    return Configuration(raw,tuple(tasks),details,tuple(sorted(events,key=lambda e:e["time"])),horizon,policy,factor)


PRESETS=("Normal operation","Simultaneous arrivals","Critical pressure","Critical infeasibility",
         "Tampered and replayed","Sensor fault","Risk escalation","Risk recovery","Overload",
         "Periodic sensors","Security versus performance")


def preset(name="Normal operation"):
    if name not in PRESETS: raise ValueError("Unknown preset")
    rows=[]
    for i,(source,kind,critical,execution,deadline,period) in enumerate([
        ("LIDAR_01","lidar","safety-critical",.25,1.,2.),("RADAR_01","radar","high",.15,.8,2.5),
        ("CAMERA_01","camera","medium",.35,1.5,3.),("IMU_01","imu","low",.10,1.,1.5)]):
        rows.append(dict(task_id=f"T{i+1}",sensor_id=source,sensor_type=kind,description=f"{kind} processing",
            criticality=critical,release=i*.1,execution=execution,deadline=deadline,period=period,
            kind="periodic",minimum_level=1,exposure=.1,health="normal",message="valid",quantum=.05,
            phases="",arrivals="",max_preemptions=100))
    events=[]
    def event(eid,target,kind,at,value=.9,duration=0):
        events.append(dict(event_id=eid,target=target,type=kind,time=at,duration=duration,value=value,
            description=kind.replace("_"," "),repeat_every=0.,job_number=0))
    if name=="Simultaneous arrivals":
        for r in rows: r["release"]=0.
    if name in {"Critical pressure","Critical infeasibility","Overload"}:
        for r in rows: r.update(release=0.,execution=.7,deadline=1.,period=1.5)
        if name in {"Critical pressure","Critical infeasibility"}:
            rows[1]["criticality"]="medium"
            rows[0]["execution"]=.3
        if name=="Critical infeasibility": rows[0].update(execution=1.2,deadline=.6)
    if name=="Tampered and replayed":
        rows[1]["message"]="tampered"
        event("replay","T3","replay",3.2)
    if name=="Sensor fault": rows[1]["health"]="faulty"
    if name in {"Risk escalation","Security versus performance"}: event("spike","T1","risk_spike",.02,1.)
    if name=="Risk recovery":
        rows[0]["exposure"]=.9; event("recovery","T1","risk_recovery",.1,.1)
    return dict(time_unit="s",horizon=15.,seed=11,algorithm="RA-LP-EDF",health_backend="RF",
                auth_cost_ms=1.,checkpoint=.05,tasks=rows,events=events,policy={})
