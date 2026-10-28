"""Separate static MPS analysis from finite released-job admission checks."""
import math
from src.scheduler.model import EPS, CRITICALITY


def edf_key(job): return (job.deadline, CRITICALITY[job.task.criticality], job.release, job.job_id)


def released_job_feasibility(jobs, now, budgets, blocking=0.0):
    """Sufficient serial-EDF envelope; current blocking is pessimistically additional.

    Covers released admitted jobs only, assuming supplied budgets bound every
    remaining path. Does NOT establish an infinite sporadic task-set guarantee.
    """
    cursor = now + blocking
    checks = []
    for job in sorted(jobs, key=edf_key):
        budget = budgets[job.job_id]
        if not math.isfinite(budget) or budget < 0:
            return {"feasible": False, "reason": "No compliant bounded mechanism", "checks": checks}
        cursor += budget
        checks.append({"job": job.job_id, "finish_bound": cursor, "deadline": job.deadline,
                       "slack": job.deadline-cursor})
        if cursor > job.deadline + EPS:
            return {"feasible": False, "reason": f"Demand exceeds deadline of {job.job_id}", "checks": checks}
    return {"feasible": True, "reason": "Released-job conservative EDF envelope holds", "checks": checks}


def mps_analysis(tasks, registry, choices, *, max_points=100000):
    """Standaert et al. §4.3 count construction + corrected Eq.9.

    Static choices only. q conservatively includes all configured per-interval
    transition extras, so nonzero extras yield a sufficient extension, not the
    reference's optimality claim. Dynamic events are outside this theorem.
    """
    if not tasks: return {"status": "feasible", "counts": {}, "points": 0, "utilization": 0.0}
    costs, counts = {}, {}
    for task in tasks:
        costs[task.task_id] = []
        for phase in task.phases:
            m = registry[choices[(task.task_id, phase.phase_id)]]
            if m.name not in phase.mechanisms or m.level < max(task.minimum_level, phase.minimum_level):
                return {"status": "infeasible", "reason": "Static mechanism violates minimum"}
            costs[task.task_id].append((phase.wcet*(1+m.execution_ratio),
                m.startup+m.teardown+m.switch+m.preemption+m.resume))
        counts[task.task_id] = [1]*len(task.phases)
    def parameters():
        c = {t.task_id: sum(base+n*q for (base,q),n in zip(costs[t.task_id],counts[t.task_id])) for t in tasks}
        b = {t.task_id: max(base/n+q for (base,q),n in zip(costs[t.task_id],counts[t.task_id])) for t in tasks}
        return c,b
    def demand(length, c):
        return sum(max(0,math.floor((length-t.deadline)/t.period+EPS)+1)*c[t.task_id] for t in tasks)
    dmax = max(t.deadline for t in tasks)
    def points(limit):
        result = set()
        for t in tasks:
            n = max(0,math.floor((limit-t.deadline)/t.period+EPS)+1)
            if n+len(result) > max_points: raise OverflowError("Analysis testing-set limit")
            result.update(t.deadline+k*t.period for k in range(n))
        return sorted(result)
    try:
        tested = 0
        for length in points(dmax):
            c,b = parameters(); slack = length-demand(length,c); tested += 1
            if slack < -EPS: return {"status": "infeasible", "reason": "Processor demand", "at": length}
            for t in tasks:
                if t.deadline > length+EPS and b[t.task_id] > slack+EPS:
                    for i,(base,q) in enumerate(costs[t.task_id]):
                        if slack <= q+EPS: return {"status": "infeasible", "reason": "Blocking cannot be reduced below transition cost", "at": length}
                        n = max(counts[t.task_id][i], math.ceil(base/(slack-q)-EPS))
                        if n > 1 and not t.phases[i].preemptible:
                            return {"status": "infeasible", "reason": "Required fixed points forbidden"}
                        counts[t.task_id][i] = n
        c,b = parameters()
        if any(sum(counts[t.task_id])-1 > t.max_preemptions for t in tasks):
            return {"status":"unknown", "reason":"Fixed points require more opportunities than configured preemption cap; theorem does not certify this cap"}
        utilization = sum(c[t.task_id]/t.period for t in tasks)
        if utilization > 1+EPS: return {"status": "infeasible", "reason": "Utilization exceeds one"}
        if all(abs(t.deadline-t.period) < EPS for t in tasks): limit = dmax
        elif utilization < 1-EPS:
            limit = max(dmax,sum(c[t.task_id]/t.period*(t.period-t.deadline) for t in tasks)/(1-utilization))
        elif all(float(t.period).is_integer() for t in tasks): limit = math.lcm(*(int(t.period) for t in tasks))
        else: return {"status": "unknown", "reason": "U=1 with noninteger periods; no finite bound implemented"}
        for length in points(limit):
            if length <= dmax+EPS: continue
            tested += 1
            blocking = min(length,max([b[t.task_id] for t in tasks if t.deadline > length] or [0]))
            if demand(length,c)+blocking > length+EPS:
                return {"status": "infeasible", "reason": "Demand/blocking test", "at": length}
        return {"status": "feasible", "counts": counts, "execution_bounds": c,
                "chunk_bounds": b, "utilization": utilization, "points": tested,
                "test_limit": limit, "scope": "static independent constrained-deadline tasks; configured cost bounds"}
    except OverflowError:
        return {"status": "unknown", "reason": "Testing-set budget exhausted, never treated as feasible"}
