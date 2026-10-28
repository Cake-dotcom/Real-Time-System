"""Run-local adapter to the production security gates. Credentials never exported."""
from collections import defaultdict
from copy import deepcopy
from types import SimpleNamespace
import secrets
import time
from src.security import sensor_system
from src.security.source_sessions import SourceSessionManager, authenticate_sender
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor
from src.security.gru_health import GRUHealthMonitor
from src.scheduler.model import Phase


class ScenarioHealth:
    """Real model by default; explicitly labelled evidence fault injection only."""
    def __init__(self, backend):
        self.backend=backend; self.condition="normal"

    def __getattr__(self,name): return getattr(self.backend,name)

    def check(self,message,features=None):
        if self.condition=="unavailable":
            return {"healthy":False,"prediction":"not_evaluated","risk_level":"unknown",
                    "issues":["Simulated unavailable model evidence"],"evidence_source":"scenario fault injection"}
        started=time.perf_counter_ns()
        result=self.backend.check(message,features=features)
        result["health_evaluation_ms"]=(time.perf_counter_ns()-started)/1e6
        if self.condition=="anomalous":
            return {**result,"healthy":False,"observed_prediction":result.get("prediction"),
                "prediction":"anomalous_reading","risk_level":"high",
                "issues":["Simulated anomalous health evidence; not a measured model classification"],
                "evidence_source":"scenario fault injection"}
        return {**result,"evidence_source":"actual configured model"}


class SecurityRuntime:
    def __init__(self,config):
        self.config=config; self.now=0.
        sources={d["sensor_id"] for d in config.details.values()}
        keys={s:secrets.token_hex(32) for s in sources}
        sessions=SourceSessionManager(keys,clock=lambda:self.now/1000)
        backend=SensorHealthMonitor() if config.original.get("health_backend","RF")=="RF" else GRUHealthMonitor()
        if config.original.get("health_backend","RF")=="RF" and backend.model_bundle is not None:
            # Single-reading inference does not benefit from a thread pool per
            # forest call. Keep worker configuration run-local; weights unchanged.
            model=backend.model_bundle["model"]
            model.set_params(**{key:1 for key in model.get_params() if key.endswith("n_jobs")})
        metadata={d["sensor_id"]:{"sensor_type":d.get("sensor_type","generic"),
            "sensor_criticality":3 if d["criticality"] in {"safety-critical","high"} else 1,"reading_unit":"m"}
            for d in config.details.values()}
        self.context=SimpleNamespace(message_monitor=MessageMonitor(keys,sessions=sessions),
            health_monitor=ScenarioHealth(backend),feature_tracker=SensorFeatureTracker(),metadata=metadata,
            critical_sources={config.details[t.task_id]["sensor_id"] for t in config.tasks if t.protected})
        self.senders={s:authenticate_sender(sessions,s,keys[s]) for s in sorted(sources)}
        self.sequence=defaultdict(int); self.accepted_packets={}; self.pending={}; self.audit={}
        self.conditions=[]; self.consumed=set(); self.committed=defaultdict(int)

    def event(self,event,sim):
        self.now=sim.now
        kind=event["type"]
        sim.log("security_event",event_id=event["event_id"],type=kind,targets=event["targets"],description=event.get("description",""))
        if kind in {"revoke_session","expire_session","reauthenticate"}:
            manager=self.context.message_monitor.sessions
            sources={self.config.details[t]["sensor_id"] for t in event["targets"]}
            for source in sorted(sources):
                if kind=="revoke_session": manager.revoke_session(source)
                elif kind=="expire_session":
                    if source in manager.sessions: manager.sessions[source].expires_at=self.now/1000
                else: self.senders[source]=authenticate_sender(manager,source,manager.sensor_keys[source])
        elif not kind.startswith("risk_"): self.conditions.append(event)

    def condition(self,job):
        row=self.config.details[job.task.task_id]
        message,health=row.get("message","valid"),row.get("health","normal")
        for event in self.conditions:
            key=(event["event_id"],job.task.task_id)
            if job.task.task_id not in event["targets"]: continue
            if event["job_number"] and job.index+1!=event["job_number"]: continue
            if event["duration"]:
                if self.now>=event["time"]+event["duration"]: continue
            elif key in self.consumed: continue
            if event["type"] in {"valid","tampered","replay","malformed"}: message=event["type"]
            else: health=event["type"]
            self.consumed.add(key)
        return message,health

    def release(self,job,sim):
        self.now=sim.now; row=self.config.details[job.task.task_id]; source=row["sensor_id"]
        condition,health=self.condition(job)
        self.context.health_monitor.condition=health
        self.sequence[source]+=1
        reading=-999 if health=="faulty" else 12.0
        message={"sensor_id":source,"sequence":self.sequence[source],"timestamp":1000+self.now/1000,
                 "distance_m":reading}
        packet=self.senders[source].sign(message)
        if condition=="replay":
            if source not in self.accepted_packets:
                self.audit[job.job_id]={"status":"SCENARIO_INVALID","reason":"Replay requires an earlier completed accepted message from this sensor",
                    "authentication":"not_evaluated","replay":"not_evaluated","accepted":False,"history_committed":False,
                    "job_id":job.job_id,"sensor":source,"time":self.now,"gate_eligible":False}
                return False,self.audit[job.job_id]["reason"]
            packet=deepcopy(self.accepted_packets[source])
        elif condition=="tampered": packet[0]["distance_m"]=13.5
        elif condition=="malformed":
            # Authentically signed malformed content exercises safe validation.
            message.pop("distance_m"); packet=self.senders[source].sign(message)
        item={"message":packet[0],"mac":packet[1],"arrival_time":job.release,
              "execution_time":sum(p.wcet for p in job.task.phases),"security_overhead":self.config.original.get("auth_cost_ms",1),
              "deadline":job.deadline,"message_age_ms":0.}
        prepared=sensor_system.process_messages([item],context=self.context,prepare_only=True)
        audit=deepcopy(prepared["messages"][0]); eligible=bool(prepared["verified_tasks"])
        audit.update(job_id=job.job_id,time=self.now,condition=condition,health_condition=health,
            gate_eligible=eligible,history_committed=False,risk_source="configured exposure and explicit simulation events",
            health_backend=self.config.original.get("health_backend","RF"))
        self.audit[job.job_id]=audit
        sim.log("security_gate",job,status=audit["status"],authentication=audit["authentication"],replay=audit["replay"],
                reason=audit["reason"],eligible=eligible)
        if not eligible: return False,str(audit["reason"])
        self.pending[job.job_id]=packet
        cost=prepared["verified_tasks"][0]["security_overhead"]
        if cost:
            phase=Phase("mandatory_validation",cost,("mandatory",),3,preemptible=False,base_category="mandatory_validation")
            job.plan.insert(0,(phase,cost))
        audit["mandatory_budget_ms"]=cost
        return True,"All production authentication, health and validation gates passed"

    def complete(self,job,sim):
        self.now=sim.now
        audit=self.audit[job.job_id]; packet=self.pending.pop(job.job_id)
        message=packet[0]; source=message["sensor_id"]
        audit.update(accepted=True,status="NORMAL",deadline_met=True,completion_time=sim.now,
                     reason="Authenticated, healthy, validated and completed before the absolute deadline")
        # A slow older reading must not overwrite newer accepted sensor history.
        if message["sequence"]>self.committed[source]:
            self.context.feature_tracker.commit_reading(message)
            self.context.health_monitor.commit_reading(message)
            self.committed[source]=message["sequence"]
            self.accepted_packets[source]=deepcopy(packet)
            audit["history_committed"]=True
            sim.log("history_commit",job,sensor=source,sequence=message["sequence"])
        else:
            audit["history_reason"]="Newer completed reading already committed; older result not added to trusted history"

    def finish(self,trace):
        self.now=trace["metrics"]["observation_interval"]
        for job in trace["jobs"]:
            audit=self.audit[job["job_id"]]
            audit["scheduler_state"]=job["state"]; audit["admitted"]=job["admitted"]
            if audit["gate_eligible"] and job["state"]!="completed":
                audit["status"]="SCHEDULING_"+job["state"].upper()
                audit["reason"]=job["transitions"][-1]["reason"]
                audit["deadline_met"]=False if job["state"]=="deadline_missed" else None
        self.pending.clear()
        return {"messages":list(self.audit.values()),"metrics":dict(self.context.message_monitor.sessions.metrics),
            "sessions":self.context.message_monitor.sessions.public_status(),
            "trusted_history_counts":{s:len(v) for s,v in self.context.feature_tracker.history.items()}}
