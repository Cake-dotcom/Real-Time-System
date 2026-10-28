"""Bounded subset admission and conservative continuation planning.

These are finite, released-job heuristics, not an optimal online scheduler.
Security gates and the fixed-point executor remain in RALPEDF.
"""
import itertools
import math
from src.scheduler.model import EPS, TERMINAL
from src.scheduler.feasibility import edf_key, released_job_feasibility
from src.scheduler.security_costs import chunk_cost, total

MODES = ("RA-LP-EDF-Admission", "RA-LP-EDF-Preemption", "RA-LP-EDF-Optimized")


def continuation_budget(sim, job, override=None):
    """A compliant continuation witness under CURRENT evidence, including dwell.

    Every interval retains startup/teardown and worst-case switch/context charges.
    Future unexpected risk changes invalidate this bound and trigger re-admission.
    Base-only elapsed time makes the projected dwell constraint conservative.
    """
    previous, changed, elapsed, demand = job.previous, job.last_switch, 0., 0.
    for index,(phase,base) in enumerate(job.plan[job.cursor:]):
        options=sim.eligible(job,phase)
        held=[m for m in options if m.name==previous]
        if held and sim.now+elapsed-changed < sim.policy.dwell: options=held
        if index==0 and override is not None:
            options=[m for m in options if m.name==override.name]
        if not options: return math.inf
        # Include the full effective cost; deterministic ties are reproducible.
        m=min(options,key=lambda m:(total(chunk_cost(base,m,previous,resumed=True,
                  decision=sim.policy.decision_cost))+m.switch+m.preemption,m.name))
        demand+=total(chunk_cost(base,m,resumed=True,decision=sim.policy.decision_cost))+m.switch+m.preemption
        if m.name!=previous: changed=sim.now+elapsed
        previous=m.name; elapsed+=base*min(job.task.actual_factor,1.)
    return demand


def subset(sim, pinned, optional):
    """Max cardinality for <=8 optional jobs; bounded heuristic for larger sets.

    Tie-breaks retain admitted work, then prefer short remaining demand and older
    releases. Critical and normal populations are optimized in separate passes.
    """
    optional=sorted(optional,key=lambda j:(not j.admitted,sim.budget(j),j.release,edf_key(j)))
    if sim.check(pinned+optional)[0]["feasible"]: return pinned+optional
    if len(optional)<=8:
        for count in range(len(optional)-1,-1,-1):
            for choice in itertools.combinations(optional,count):
                if sim.check(pinned+list(choice))[0]["feasible"]: return pinned+list(choice)
        return pinned
    chosen=list(pinned)
    for job in sorted(optional,key=edf_key):
        proposed=chosen+[job]
        verdict,_=sim.check(proposed)
        if verdict["feasible"]: chosen=proposed; continue
        # Exchange the largest removable demand in the first violating prefix.
        cutoff=verdict["checks"][-1]["deadline"] if verdict["checks"] else job.deadline
        removable=[j for j in proposed if j not in pinned and j.deadline<=cutoff+EPS]
        if removable:
            drop=max(removable,key=lambda j:(sim.budget(j),not j.admitted,-j.release,j.job_id))
            proposed.remove(drop)
            if sim.check(proposed)[0]["feasible"]: chosen=proposed
    return chosen


def admit(sim):
    available=[j for j in sim.jobs if j.release<=sim.now+EPS and j.state not in TERMINAL and j.state!="created"]
    running=sim.block["job"] if sim.block and not sim.block["cleanup"] else None
    pinned=[running] if running in available else []
    if sim.last in available and sim.last not in pinned and (not sim.policy.preemption or sim.last.preemptions>=sim.last.task.max_preemptions):
        pinned.append(sim.last)
    critical=[j for j in available if j.task.protected and j not in pinned]
    chosen=subset(sim,pinned,critical)
    # Only spend spare capacity after the protected subset is feasible.
    normals=[j for j in available if not j.task.protected and j not in pinned]
    chosen=subset(sim,chosen,normals)
    dropped=[j for j in available if j not in chosen]
    if dropped and sim.overload_start is None:
        sim.overload_start=sim.now; sim.log("overload",reason="Released demand exceeds selected feasible subset")
    for j in dropped:
        reason="Deferred by critical-first feasible-subset admission; retry at next event"
        if not math.isfinite(sim.budget(j)):
            sim.fail(j,"No compliant bounded mechanism","rejected" if j.state in {"pending","deferred"} else "failed")
            continue
        if j is sim.last and j.state=="ready":
            sim.interrupt(j,"Capacity reclaimed for feasible critical-first subset")
        if j.state!="deferred":
            j.transition("deferred",sim.now,reason)
            sim.log("deferred",j,reason=reason,remaining_bound=sim.budget(j),deadline=j.deadline)
        # Do not call a failed sufficient test inherent infeasibility. If even
        # this job alone cannot pass our bound now, record the precise failure.
        if j.task.protected:
            verdict,_=sim.check([j])
            if not verdict["feasible"] and running is None:
                sim.fail(j,"Protected admission bound failed: "+verdict["reason"],"rejected")
    for j in chosen:
        if j.state in {"pending","deferred"}:
            verdict,_=sim.check(chosen)
            first=not j.admitted; j.admitted=True
            j.transition("ready",sim.now,"Critical-first feasible subset selected")
            sim.log("admitted" if first else "recovered",j,feasibility=verdict,
                    reason="Protected cardinality first, then total cardinality; released-job bound")
    active=sim.active(); verdict,budgets=sim.check(active)
    if sim.policy.reservations:
        sim.ledger.update(active,budgets,sim.now)
        for j in active:
            if j.task.protected: j.reservation_peak=max(j.reservation_peak,budgets[j.job_id])
    if sim.overload_start is not None and not dropped and verdict["feasible"]:
        sim.recovery_times.append(sim.now-sim.overload_start)
        sim.log("overload_recovered",duration=sim.recovery_times[-1]); sim.overload_start=None


def continue_without_preemption(sim, active):
    """Continue the previous job only if completing it FIRST still fits everyone.

    This deliberately conservative test avoids speculative intra-interval stops.
    Actual decisions are rechecked at each fixed point and on every new event.
    """
    last=sim.last
    if last not in active or last.state!="ready": return False
    budgets={j.job_id:sim.budget(j) for j in active}
    first=budgets[last.job_id]
    if sim.now+first>last.deadline+EPS: return False
    rest=[j for j in active if j is not last]
    verdict=released_job_feasibility(rest,sim.now,budgets,first)
    if verdict["feasible"]:
        sim.log("preemption_avoided",last,reason="Complete-current-first bound preserves all released deadlines",feasibility=verdict)
        return True
    return False
