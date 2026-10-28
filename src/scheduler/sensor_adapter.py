"""Adapter called only after production authentication, health and policy gates.

Scheduling is simulated. Upstream mandatory validation cost is retained exactly
once as an opaque phase; simulated mechanisms do not replace real authentication.
No calibrated threat feed exists in the receiver: exposure is unknown (strong).
"""
from src.scheduler.model import Task, Phase
from src.scheduler.security_costs import Mechanism, default_registry
from src.scheduler.dynamic_risk import Policy
from src.scheduler.ra_lp_edf import RALPEDF


def schedule_sensor_tasks(verified_tasks):
    registry=default_registry()
    registry["mandatory"]=Mechanism("mandatory",3,0,0,0,0,0,0,.9,
        provenance="Upstream mandatory validation and handshake simulated budget")
    tasks=[]; expired=[]
    for item in verified_tasks:
        relative=item["deadline"]-item["arrival_time"]
        if relative<=0:
            expired.append(item); continue
        phases=[]
        if item["security_overhead"]>0:
            phases.append(Phase("mandatory_validation",item["security_overhead"],("mandatory",),3,preemptible=False,base_category="mandatory_validation"))
        if item["execution_time"]>0:
            phases.append(Phase("application",item["execution_time"],quantum=1))
        if not phases:
            raise ValueError("Sensor task must contain positive work")
        tasks.append(Task(item["task_id"],tuple(phases),relative,relative,
            release=item["arrival_time"],kind="oneshot",safety_critical=item["critical"],
            exposure=None,sensor_type=item["sensor"]))
    horizon=max([i["deadline"] for i in verified_tasks]+[1])
    trace=RALPEDF(tasks,registry=registry,policy=Policy(ttl=max(1,horizon+1)),horizon=horizon).run()
    completed=[j for j in trace["jobs"] if j["state"]=="completed"]
    deferred=[j["task_id"] for j in trace["jobs"] if j["state"]!="completed"]
    deferred += [i["task_id"] for i in expired]
    critical_failed=any(j["critical"] and j["state"]!="completed" for j in trace["jobs"]) or any(i["critical"] for i in expired)
    return {"mode":"CRITICAL_DEADLINE_FAILURE" if critical_failed else "CRITICAL_ONLY" if deferred else "ALL_SENSORS",
        "algorithm":"RA-LP-EDF", "results":[{"task_id":j["task_id"],"start":j["start"],"finish":j["finish"],
            "deadline":j["deadline"],"deadline_met":True} for j in completed],
        "deferred_sensors":deferred,"research":trace,
        "expired_before_release":[i["task_id"] for i in expired]}
