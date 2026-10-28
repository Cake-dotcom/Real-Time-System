"""Event-driven fixed-preemption-point EDF with risk-aware admission and budgets.

Security mechanisms here are cost/capability models, NOT executed cryptography.
Mandatory real source authentication stays upstream in sensor_system.
"""
import math
import time
from src.scheduler.model import EPS, TERMINAL, CRITICALITY, generate_jobs
from src.scheduler.dynamic_risk import Policy, RiskState
from src.scheduler.security_costs import default_registry, chunk_cost, total
from src.scheduler.feasibility import edf_key, released_job_feasibility
from src.scheduler.reservations import ReservationLedger


class RALPEDF:
    def __init__(self, tasks, risk_events=(), *, policy=None, registry=None, horizon=100,
                 release_hook=None, completion_hook=None, external_events=(), event_hook=None,
                 capture_snapshots=False, cache_budgets=True):
        self.release_hook, self.completion_hook = release_hook, completion_hook
        self.external_events = sorted(external_events, key=lambda e:e["time"])
        self.event_hook, self.capture_snapshots = event_hook, capture_snapshots
        self.snapshots = []
        self.policy = policy or Policy()
        self.registry = registry or default_registry()
        self.jobs = generate_jobs(tasks, horizon)
        self.tasks = {t.task_id:t for t in tasks}
        self.risk = {t.task_id:RiskState(t,self.policy) for t in tasks}
        self.risk_events = sorted(risk_events, key=lambda e:e.time)
        if any(e.task_id not in self.tasks for e in self.risk_events): raise ValueError("Risk event for unknown task")
        for t in tasks:
            for p in t.phases:
                if any(m not in self.registry for m in p.mechanisms): raise ValueError("Unknown mechanism")
        self.horizon, self.now = horizon, 0.0
        self.events, self.timeline = [], []
        self.ledger = ReservationLedger()
        self.block = None
        self.last = None
        self.runtime_ns = 0
        self.decision_ns = 0
        self.safe_states = 0
        self.overload_start = None
        self.recovery_times = []
        self.risk_integral = 0.0
        self.compliant_time = 0.0
        self.protected_time = 0.0
        self.selection_details = {}
        from src.scheduler.optimization import MODES
        self.optimized = self.policy.mode in MODES
        self.adaptive_subset = self.policy.mode in {"RA-LP-EDF-Admission", "RA-LP-EDF-Optimized"}
        self.efficient_cost = self.policy.mode == "RA-LP-EDF-Optimized"
        self.lazy_preemption = self.policy.mode in {"RA-LP-EDF-Preemption", "RA-LP-EDF-Optimized"}
        self.cache_budgets = cache_budgets and self.optimized
        self.budget_cache = {}
        self.counters = {"budget_evaluations":0,"budget_cache_hits":0,"feasibility_checks":0}

    def log(self, event, job=None, **extra):
        self.events.append({"time": self.now, "event": event, "job": job.job_id if job else None, **extra})

    def active(self):
        return [j for j in self.jobs if j.admitted and j.state not in TERMINAL and j.state != "deferred"]

    def level(self, job, phase):
        risk, level, uncertain = self.risk[job.task.task_id].assess(self.now)
        return risk, max(level, phase.minimum_level, job.task.minimum_level)

    def eligible(self, job, phase):
        _, required = self.level(job,phase)
        mechanisms = [self.registry[name] for name in phase.mechanisms if self.registry[name].level >= required]
        if phase.base_category == "mandatory_validation": return mechanisms
        mode = self.policy.mode
        if mode in {"Static-Sec-EDF", "MPS-LP-EDF-structural", "Highest-security"}:
            mechanisms = [m for m in mechanisms if m.level == 3]
        elif mode == "Standard-EDF":
            # Fixed light mechanism; reject when risk requires more, never silently run insecurely.
            mechanisms = [m for m in mechanisms if m.level == 1]
        return mechanisms

    def budget(self, job, override=None):
        if self.optimized:
            # Epoch cache is cleared before every decision batch. Cursor changes
            # in check(), real resume state and dwell transitions are in the key.
            key=(job.job_id,job.cursor,job.previous,job.last_switch,job.needs_resume,
                 job.preemptions,len(job.plan),override.name if override else None)
            if self.cache_budgets and key in self.budget_cache:
                self.counters["budget_cache_hits"]+=1
                return self.budget_cache[key]
            self.counters["budget_evaluations"]+=1
            if self.efficient_cost:
                from src.scheduler.optimization import continuation_budget
                value=continuation_budget(self,job,override)
            else:
                value=self.original_budget(job,override)
            if self.cache_budgets: self.budget_cache[key]=value
            return value
        return self.original_budget(job,override)

    def original_budget(self, job, override=None):
        budget = 0.0
        for k,(phase,base) in enumerate(job.plan[job.cursor:], job.cursor):
            options = self.eligible(job,phase)
            if not options: return math.inf
            if override is not None and k == job.cursor and not (job.task.protected and self.policy.reservations):
                options = [override]
            costs = []
            for m in options:
                # Reserve switching and actual context-switch overhead conservatively per interval.
                c = chunk_cost(base,m,resumed=True,decision=self.policy.decision_cost)
                costs.append(total(c)+m.switch+m.preemption)
            budget += max(costs) if job.task.protected and self.policy.reservations else min(costs)
        return budget

    def check(self, jobs, candidate=None, mechanism=None):
        if self.optimized: self.counters["feasibility_checks"]+=1
        budgets = {j.job_id:self.budget(j, mechanism if j is candidate else None) for j in jobs}
        blocking = 0.0
        if self.block:
            blocking = self.block["end"]-self.now
            current = self.block["job"]
            if not self.block["cleanup"] and current in jobs:
                # The running interval is paid once, ahead of EDF demand. Bound
                # only its suffix here; never charge the full interval twice.
                current.cursor += 1
                try:
                    budgets[current.job_id] = self.budget(current)
                finally:
                    current.cursor -= 1
                if not self.policy.preemption or current.preemptions >= current.task.max_preemptions:
                    # A reached cap locks the entire remaining job, not merely
                    # its current fixed interval. Later releases must see that.
                    blocking += budgets[current.job_id]
                    budgets[current.job_id] = 0.0
        elif self.last in jobs and (not self.policy.preemption or self.last.preemptions >= self.last.task.max_preemptions):
            blocking = budgets[self.last.job_id]
            budgets[self.last.job_id] = 0.0
        if self.optimized:
            outgoing=self.block["job"] if self.block and not self.block["cleanup"] else (self.last if not self.block else None)
            if outgoing is not None and outgoing not in jobs and outgoing.state not in TERMINAL:
                if not self.policy.preemption or outgoing.preemptions>=outgoing.task.max_preemptions:
                    # A locked suffix cannot be wished away by subset admission.
                    outgoing.cursor+=int(bool(self.block))
                    try: blocking+=self.budget(outgoing)
                    finally: outgoing.cursor-=int(bool(self.block))
                elif outgoing.previous:
                    blocking+=self.registry[outgoing.previous].preemption
        result = released_job_feasibility(jobs,self.now,budgets,blocking)
        if self.block and not self.block["cleanup"] and self.block["job"] in jobs:
            budgets[self.block["job"].job_id] += blocking
        elif self.last in jobs and (not self.policy.preemption or self.last.preemptions >= self.last.task.max_preemptions):
            budgets[self.last.job_id] += blocking
        return result,budgets

    def fail(self, job, reason, state="failed"):
        if job.state in TERMINAL: return
        job.transition(state,self.now,reason)
        self.log(state,job,reason=reason)
        if job.task.protected:
            self.safe_states += 1
            self.log("safe_state",job,reason="Protected workload infeasible: " + reason)

    def adapt_and_admit(self):
        self.budget_cache.clear()
        if self.adaptive_subset and self.policy.admission and self.policy.overload:
            from src.scheduler.optimization import admit
            return admit(self)
        # Check all admitted demand after every event, shedding only noncritical work first.
        active = self.active()
        verdict,budgets = self.check(active)
        if not verdict["feasible"] and self.policy.overload:
            if self.overload_start is None: self.overload_start = self.now; self.log("overload")
            for job in sorted(active,key=lambda j:(CRITICALITY[j.task.criticality],j.deadline),reverse=True):
                if job.task.protected or (self.block and self.block["job"] is job): continue
                if self.optimized and job is self.last:
                    if not self.policy.preemption or job.preemptions>=job.task.max_preemptions: continue
                    if job.state=="ready": self.interrupt(job,"Capacity reclaimed after demand change")
                job.transition("deferred",self.now,"Reclaim noncritical capacity")
                self.log("deferred",job,reason=verdict["reason"])
                active = self.active(); verdict,budgets = self.check(active)
                if verdict["feasible"]: break
            if not verdict["feasible"]:
                # Do not conceal that existing critical assumptions have been invalidated.
                for job in list(active):
                    if self.block and self.block["job"] is job: continue
                    self.fail(job,"Risk/cost change invalidated protected feasibility")
                active = self.active(); verdict,budgets = self.check(active)
        for job in sorted([j for j in self.jobs if j.state in {"pending","deferred"}],
                          key=lambda j:(not j.task.protected, *edf_key(j))):
            if job.deadline <= self.now+EPS:
                self.fail(job,"Deferral deadline expired","deadline_missed"); continue
            result, proposed = self.check(self.active()+[job])
            if result["feasible"] or not self.policy.admission:
                job.transition("ready",self.now,result["reason"])
                first = not job.admitted
                job.admitted = True
                self.log("admitted" if first else "recovered",job,feasibility=result)
            elif not math.isfinite(proposed[job.job_id]) or job.task.protected:
                self.fail(job,result["reason"],"rejected")
            else:
                if job.state != "deferred":
                    job.transition("deferred",self.now,result["reason"])
                    self.log("deferred",job,reason=result["reason"])
                    if self.overload_start is None: self.overload_start = self.now; self.log("overload")
        active = self.active(); _,budgets = self.check(active)
        if self.policy.reservations:
            self.ledger.update(active,budgets,self.now)
            for job in active:
                if job.task.protected: job.reservation_peak = max(job.reservation_peak,budgets[job.job_id])
        if self.overload_start is not None and not any(j.state == "deferred" for j in self.jobs) and verdict["feasible"]:
            self.recovery_times.append(self.now-self.overload_start)
            self.log("overload_recovered",duration=self.recovery_times[-1]); self.overload_start = None

    def choose_mechanism(self, job):
        phase,base = job.plan[job.cursor]
        risk,required = self.level(job,phase)
        candidates = []
        evaluated = []
        for m in self.eligible(job,phase):
            feasible,_ = self.check(self.active(),job,m)
            evaluated.append({"mechanism":m.name,"timing_feasible":feasible["feasible"],"timing_reason":feasible["reason"]})
            if not feasible["feasible"] and self.policy.admission: continue
            cost = chunk_cost(base,m,job.previous,resumed=job.needs_resume if self.optimized else False,decision=self.policy.decision_cost)
            switch_penalty = cost["switch"] if self.policy.switch_aware else 0.0
            objective = self.policy.alpha*risk*(1-m.effectiveness) + self.policy.beta*(total(cost)-base) + self.policy.gamma*switch_penalty
            if self.policy.mode == "SAEDF-style": objective = -m.level
            if self.policy.mode in {"Minimum-security", "No-switch-awareness"}: objective = total(cost) if self.policy.mode == "Minimum-security" else objective
            if self.efficient_cost: objective=total(cost)
            candidates.append((objective,total(cost),m.name,m))
            evaluated[-1].update(objective=objective,interval_cost=total(cost))
        self.selection_details={"risk":risk,"required_level":required,"evaluated":evaluated,
                                "selection_rule":"least full interval cost subject to mandatory protection and feasible continuation" if self.efficient_cost else "minimum configured objective"}
        if not candidates: return None
        # Mechanism dwell never suppresses an obligatory security upgrade.
        previous = self.registry.get(job.previous)
        if previous and previous.level >= required and self.now-job.last_switch < self.policy.dwell:
            matches = [r for r in candidates if r[2] == previous.name]
            if matches:
                self.selection_details["selection_rule"]="retain compliant feasible mechanism during dwell"
                return matches[0][3]
        return min(candidates,key=lambda r:r[:3])[3]

    def interrupt(self, outgoing, reason):
        outgoing.transition("preempted",self.now,reason)
        outgoing.preemptions+=1; outgoing.needs_resume=True
        self.log("preempted",outgoing,reason=reason)
        overhead=self.registry[outgoing.previous].preemption
        self.last=None
        if overhead>EPS:
            self.block={"job":outgoing,"start":self.now,"end":self.now+overhead,
                        "costs":{"preemption":overhead},"mechanism":None,"cleanup":True}

    def dispatch(self):
        active = self.active()
        if not active: return
        chosen = min(active,key=edf_key)
        dispatch_rule="EDF at a fixed preemption point"
        if self.lazy_preemption and chosen is not self.last:
            from src.scheduler.optimization import continue_without_preemption
            if continue_without_preemption(self,active):
                chosen=self.last
                dispatch_rule="Retain current job: complete-current-first bound preserves all released deadlines"
        if self.last in active and (not self.policy.preemption or self.last.preemptions >= self.last.task.max_preemptions):
            if chosen is not self.last: self.log("preemption_forbidden",self.last,waiting=chosen.job_id)
            chosen = self.last
            dispatch_rule="Current job locked by preemption policy/cap"
        if self.last in active and self.last is not chosen and self.last.state == "ready":
            outgoing = self.last
            outgoing.transition("preempted",self.now,"Earlier-deadline eligible job")
            outgoing.preemptions += 1
            outgoing.needs_resume = True
            self.log("preempted",outgoing,by=chosen.job_id)
            overhead = self.registry[outgoing.previous].preemption
            self.last = None
            if overhead > EPS:
                self.block = {"job":outgoing,"start":self.now,"end":self.now+overhead,
                              "costs":{"preemption":overhead},"mechanism":None,"cleanup":True}
                return
        m = self.choose_mechanism(chosen)
        if m is None:
            self.fail(chosen,"No feasible compliant mechanism"); return
        phase,base = chosen.plan[chosen.cursor]
        resumed = chosen.needs_resume
        costs = chunk_cost(base*min(chosen.task.actual_factor,1.0),m,chosen.previous,
                           resumed=resumed,decision=self.policy.decision_cost)
        chosen.needs_resume = False
        if phase.base_category != "base": costs[phase.base_category] = costs.pop("base")
        if chosen.previous != m.name:
            if chosen.previous is not None:
                chosen.switches += 1
                self.log("mechanism_switch",chosen,previous=chosen.previous,selected=m.name)
            chosen.last_switch = self.now
        chosen.previous = m.name
        chosen.transition("running",self.now,"EDF dispatch at fixed preemption point")
        if chosen.start is None: chosen.start = self.now
        self.block = {"job":chosen,"start":self.now,"end":self.now+total(costs),"costs":costs,
                      "mechanism":m,"phase":phase.phase_id,"cleanup":False}
        self.log("dispatch",chosen,phase=phase.phase_id,mechanism=m.name,
                 required=self.level(chosen,phase)[1],remaining_base=chosen.remaining_base,costs=costs,
                 selection=self.selection_details,
                 reason=dispatch_rule+"; "+self.selection_details["selection_rule"] if self.optimized else "Earliest eligible deadline subject to fixed-point/cap constraints; compliant mechanism selected by configured objective and dwell")

    def advance(self, destination):
        if self.block:
            b = self.block; job = b["job"]; dt = destination-self.now
            allocated = {}
            cursor = b["start"]
            for name in ("scheduler", "switch", "resume", "preemption", "startup", "mandatory_validation", "base", "security_execution", "teardown"):
                value = b["costs"].get(name,0.0)
                allocated[name] = max(0.0, min(destination,cursor+value)-max(self.now,cursor))
                cursor += value
            for name,value in allocated.items(): job.costs[name] = job.costs.get(name,0.0)+value
            self.ledger.consume(job.job_id,sum(allocated.values()))
            risk,required = self.level(job,job.plan[job.cursor][0])
            m = b["mechanism"]
            self.timeline.append({"start":self.now,"end":destination,"job":job.job_id,
                 "phase":b.get("phase"),"mechanism":m.name if m else "transition",
                 "required":required,"risk":risk,"costs":allocated,"cleanup":b["cleanup"]})
            if m:
                self.protected_time += dt
                self.compliant_time += dt*int(m.level >= required)
                self.risk_integral += dt*risk*(1-m.effectiveness)
        elif destination > self.now:
            self.timeline.append({"start":self.now,"end":destination,"job":None,"costs":{}})
        self.now = destination

    def run(self):
        started = time.perf_counter_ns()
        risk_index = 0
        external_index = 0
        iterations = 0
        while (any(j.state not in TERMINAL for j in self.jobs) or
               external_index < len(self.external_events)):
            iterations += 1
            if iterations > 1000000: raise RuntimeError("Simulation event budget exhausted")
            # Complete intervals before same-time releases/risk/deadlines.
            if self.block and self.block["end"] <= self.now+EPS:
                b,self.block = self.block,None; job = b["job"]
                if not b["cleanup"]:
                    if job.task.actual_factor > 1+EPS:
                        self.log("budget_overrun",job); self.fail(job,"Configured WCET exhausted; safe stop")
                    else:
                        job.cursor += 1
                        if job.cursor == len(job.plan):
                            job.finish = self.now; job.transition("completed",self.now,"All phases complete")
                            self.log("completed",job)
                            if self.completion_hook: self.completion_hook(job,self)
                        else:
                            job.transition("ready",self.now,"Fixed point: teardown complete")
                            self.last = job
            while external_index < len(self.external_events) and self.external_events[external_index]["time"] <= self.now+EPS:
                event = self.external_events[external_index]; external_index += 1
                if self.event_hook: self.event_hook(event,self)
            while risk_index < len(self.risk_events) and self.risk_events[risk_index].time <= self.now+EPS:
                event = self.risk_events[risk_index]; risk_index += 1
                if self.policy.dynamic: self.risk[event.task_id].update(event)
                self.log("risk_event",task=event.task_id,exposure=event.exposure,applied=self.policy.dynamic)
            for job in self.jobs:
                if job.state == "created" and job.release <= self.now+EPS:
                    job.transition("pending",self.now,"Job released"); self.log("release",job,deadline=job.deadline)
                    if self.release_hook:
                        allowed,reason = self.release_hook(job,self)
                        if not allowed:
                            self.log("security_rejected",job,reason=reason)
                            self.fail(job,reason,"rejected")
            # Risk event inside an atomic secure region: fail-stop, never execute under-strength.
            if self.block and not self.block["cleanup"]:
                b = self.block; job = b["job"]
                required = self.level(job,job.plan[job.cursor][0])[1]
                if b["mechanism"].level < required or job.deadline <= self.now+EPS:
                    reason = "Risk upgrade inside non-preemptive region" if b["mechanism"].level < required else "Deadline reached"
                    job.transition("suspended",self.now,reason)
                    self.log("security_suspension",job,reason=reason)
                    self.fail(job,reason,"failed" if "Risk" in reason else "deadline_missed")
                    # The unexecuted portion of the already-budgeted teardown must still run.
                    cleanup = min(b["costs"].get("teardown",0),max(0,b["end"]-self.now))
                    self.block = ({"job":job,"start":self.now,"end":self.now+cleanup,
                                   "costs":{"teardown":cleanup},"mechanism":None,"cleanup":True}
                                  if cleanup > EPS else None)
            for job in self.jobs:
                if job.state not in TERMINAL and job.release <= self.now and job.deadline <= self.now+EPS:
                    self.fail(job,"Absolute deadline reached","deadline_missed")
            decision_started = time.perf_counter_ns()
            self.adapt_and_admit()
            while not self.block and self.active():
                self.dispatch()
            self.decision_ns += time.perf_counter_ns()-decision_started
            if self.capture_snapshots: self.snapshot()
            if not self.block and all(j.state in TERMINAL for j in self.jobs) and external_index == len(self.external_events): break
            times = [j.release for j in self.jobs if j.state == "created" and j.release > self.now+EPS]
            times += [j.deadline for j in self.jobs if j.state not in TERMINAL and j.deadline > self.now+EPS]
            if risk_index < len(self.risk_events): times.append(self.risk_events[risk_index].time)
            if external_index < len(self.external_events): times.append(self.external_events[external_index]["time"])
            if self.policy.dynamic:
                times += [r.updated+self.policy.ttl for r in self.risk.values() if r.updated+self.policy.ttl > self.now+EPS]
            if self.block: times.append(self.block["end"])
            if not times:
                if self.active(): continue
                break
            self.advance(min(times))
        # Drain security cleanup even after the last job is failed.
        if self.block:
            self.advance(self.block["end"]); self.block = None
        if self.capture_snapshots and self.now < self.horizon:
            self.advance(self.horizon)
            if self.jobs or self.snapshots: self.snapshot()
        self.ledger.update([],{},self.now)
        self.runtime_ns = time.perf_counter_ns()-started
        from src.scheduler.scheduling_metrics import summarize
        return {"algorithm":self.policy.mode,"jobs":[self.job_record(j) for j in self.jobs],
                "events":self.events,"timeline":self.timeline,"reservations":self.ledger.events,
                "risk_history":{k:r.history for k,r in self.risk.items()},"metrics":summarize(self),
                "snapshots":self.snapshots}

    def snapshot(self):
        rows=[]
        live_budgets=self.check(self.active())[1] if self.optimized else {}
        for j in self.jobs:
            if j.release > self.now+EPS: continue
            remaining=0 if j.state=="completed" else max(0,sum(c for _,c in j.plan)-j.costs.get("base",0)-j.costs.get("mandatory_validation",0))
            risk,required=self.risk[j.task.task_id].assess(self.now)[:2]
            bound=0 if j.state in TERMINAL else (live_budgets[j.job_id] if j.job_id in live_budgets else self.budget(j))
            rows.append({"job_id":j.job_id,"state":j.state,"release":j.release,"deadline":j.deadline,
                "criticality":j.task.criticality,"critical":j.task.protected,"risk":risk,
                "required":max(required,j.plan[min(j.cursor,len(j.plan)-1)][0].minimum_level),
                "remaining_base":remaining,"remaining_bound":bound if math.isfinite(bound) else None,
                "slack":j.deadline-self.now-bound if math.isfinite(bound) else None})
            rows[-1].update(admitted=j.admitted,mechanism=j.previous,preemptions=j.preemptions,
                reservation=self.ledger.entries.get(j.job_id),
                remaining_security_bound=max(0,bound-remaining) if math.isfinite(bound) else None,
                latest_reason=j.transitions[-1]["reason"] if j.transitions else None)
        ready=sorted([r for r in rows if r["state"] in {"ready","preempted"}],
                     key=lambda r:(r["deadline"],CRITICALITY[r["criticality"]],r["release"],r["job_id"]))
        self.snapshots.append({"time":self.now,"jobs":rows,"ready":ready,
            "running":self.block["job"].job_id if self.block and not self.block["cleanup"] else None,
            "safe_state_events":self.safe_states})

    def job_record(self,j):
        return {"job_id":j.job_id,"task_id":j.task.task_id,"release":j.release,"deadline":j.deadline,
                "criticality":j.task.criticality,"minimum_level":j.task.minimum_level,
                "configured_base":sum(p.wcet for p in j.task.phases),
                "state":j.state,"admitted":j.admitted,"critical":j.task.protected,"start":j.start,
                "finish":j.finish,"remaining_base":0 if j.state=="completed" else max(0,sum(c for _,c in j.plan)-j.costs.get("base",0)-j.costs.get("mandatory_validation",0)),"costs":j.costs,
                "preemptions":j.preemptions,"switches":j.switches,"transitions":j.transitions,
                "reservation_peak":j.reservation_peak}
