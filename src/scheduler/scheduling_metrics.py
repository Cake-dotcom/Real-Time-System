"""Explicit finite-release-population metrics. Undefined ratios return None."""
import statistics


def ratio(n,d): return n/d if d else None


def summarize(sim):
    jobs = sim.jobs; completed = [j for j in jobs if j.state == "completed"]
    admitted = [j for j in jobs if j.admitted]; critical = [j for j in jobs if j.task.protected]
    missed = [j for j in jobs if j.state == "deadline_missed"]
    costs = {}
    for j in jobs:
        for k,v in j.costs.items(): costs[k] = costs.get(k,0.0)+v
    responses = [j.finish-j.release for j in completed]
    end = max(sim.horizon, sim.now)
    events = sim.events
    return {"released_jobs":len(jobs),"admitted_jobs":len(admitted),"completed_jobs":len(completed),
        "on_time_jobs":sum(j.finish<=j.deadline+1e-9 for j in completed),
        "critical_on_time_ratio":ratio(sum(j.task.protected for j in completed),len(critical)),
        "critical_noncompletion_ratio":ratio(sum(j.state!="completed" for j in critical),len(critical)),
        "noncompletion_ratio":ratio(len(jobs)-len(completed),len(jobs)),
        "admitted_noncompletion_jobs":sum(j.state!="completed" for j in admitted),
        "never_admitted_jobs":sum(not j.admitted for j in jobs),
        "rejected_jobs":sum(j.state=="rejected" for j in jobs),
        "ever_deferred_jobs":len({e['job'] for e in events if e['event']=='deferred'}),
        "security_rejected_jobs":sum(e['event']=='security_rejected' for e in events),
        "infeasible_admissions":sum(e['event']=='admitted' and not e.get('feasibility',{}).get('feasible',True) for e in events),
        "by_criticality":{c:{"released":sum(j.task.criticality==c for j in jobs),
            "admitted":sum(j.task.criticality==c for j in admitted),
            "on_time":sum(j.task.criticality==c for j in completed),
            "noncompletion":sum(j.task.criticality==c and j.state!='completed' for j in jobs)}
            for c in ("critical","high","normal","low")},
        "decision_counters":getattr(sim,"counters",{}),
        "critical_jobs":len(critical),"deadline_misses":len(missed),
        "critical_completed_jobs":sum(j.task.protected for j in completed),
        "critical_rejected_jobs":sum(j.state=="rejected" for j in critical),
        "critical_failed_jobs":sum(j.state=="failed" for j in critical),
        "deadline_miss_ratio":ratio(len(missed),len(jobs)),
        "critical_deadline_miss_ratio":ratio(sum(j.task.protected for j in missed),len(critical)),
        "admitted_on_time_ratio":ratio(len(completed),len(admitted)),
        "released_on_time_ratio":ratio(len(completed),len(jobs)),
        "finite_trace_success":bool(jobs) and len(completed)==len(jobs),
        "response_mean":statistics.mean(responses) if responses else None,
        "response_max":max(responses) if responses else None,
        "response_p95":sorted(responses)[min(len(responses)-1,int(.95*len(responses)))] if responses else None,
        "observation_interval":end,"simulated_cpu_utilization":ratio(sum(costs.values()),end),
        "idle_time":end-sum(costs.values()),"cost_categories":costs,
        "security_overhead":sum(v for k,v in costs.items() if k not in {"base","scheduler"}),
        "residual_risk_time_integral":sim.risk_integral,
        "mean_residual_risk_while_executing":ratio(sim.risk_integral,sim.protected_time),
        "security_compliance":ratio(sim.compliant_time,sim.protected_time),
        "preemptions":sum(j.preemptions for j in jobs),"mechanism_switches":sum(j.switches for j in jobs),
        "rejection_ratio":ratio(sum(j.state=="rejected" for j in jobs),len(jobs)),
        "ever_deferred_ratio":ratio(len({e['job'] for e in events if e['event']=='deferred'}),len(jobs)),
        "overload_events":sum(e['event']=='overload' for e in events),
        "overload_recovery_durations":sim.recovery_times,"safe_state_events":sim.safe_states,
        "failed_jobs":sum(j.state=="failed" for j in jobs),
        "reservation_utilization":ratio(sim.ledger.consumed_total,sim.ledger.reserved_total),
        "reservation_violations":sim.ledger.violations,
        "simulation_wall_ms":sim.runtime_ns/1e6,
        "scheduler_wall_ms":sim.decision_ns/1e6,
        "formal_dynamic_schedulability":None}
