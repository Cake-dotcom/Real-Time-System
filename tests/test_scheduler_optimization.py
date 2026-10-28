import pytest
from dataclasses import replace
from src.scheduler.model import Task, Phase
from src.scheduler.dynamic_risk import Policy, RiskEvent
from src.scheduler.experiments import run_algorithm, workload
from src.scheduler.optimization import MODES


def task(name,c,d,critical=False,release=0,q=1,**kwargs):
    return Task(name,(Phase("p",c,quantum=q),),max(d,20),d,release=release,
                kind="oneshot",safety_critical=critical,**kwargs)


def run(tasks, mode="RA-LP-EDF-Optimized", events=(), **kwargs):
    return run_algorithm(tasks,events,mode,horizon=20,**kwargs)


def audit(t):
    jobs=t["jobs"]; m=t["metrics"]
    assert all(j["finish"]<=j["deadline"]+1e-9 for j in jobs if j["state"]=="completed")
    assert sum(j["state"]=="completed" for j in jobs)==m["completed_jobs"]
    assert m["security_compliance"] in (None,1.)
    assert m["reservation_violations"]==0
    assert sum(sum(j["costs"].values()) for j in jobs)==pytest.approx(sum(i["end"]-i["start"] for i in t["timeline"] if i["job"]))
    for j in jobs:
        dispatched=[e for e in t["events"] if e["event"]=="dispatch" and e["job"]==j["job_id"]]
        if j["state"]=="completed":
            for key in ("startup","teardown","switch","resume"):
                assert j["costs"].get(key,0)==pytest.approx(sum(e["costs"][key] for e in dispatched))
        assert j["costs"].get("preemption",0)==pytest.approx(j["preemptions"]*.02)


def test_critical_current_requirement_budget_avoids_strongest_reservation_rejection():
    tasks=[task("critical",4,5,True)]
    assert run(tasks,"RA-LP-EDF")["metrics"]["completed_jobs"]==0
    t=run(tasks); assert t["metrics"]["critical_completed_jobs"]==1; audit(t)
    assert {e["mechanism"] for e in t["events"] if e["event"]=="dispatch"}=={"light"}


def test_subset_admission_saves_two_short_jobs_instead_of_one_long_job():
    tasks=[task("A",4,6),task("B",2,6),task("C",2,6)]
    assert run(tasks,"RA-LP-EDF")["metrics"]["completed_jobs"]==1
    t=run(tasks,"RA-LP-EDF-Admission")
    assert t["metrics"]["completed_jobs"]==2; audit(t)


def test_critical_subset_survives_collective_overload():
    t=run([task("A",4,6,True),task("B",2,6,True),task("C",2,6,True)])
    assert t["metrics"]["critical_completed_jobs"]==2
    assert t["metrics"]["safe_state_events"]>=1; audit(t)


def test_lazy_preemption_saves_context_cost_without_moving_points():
    tasks=[task("A",5,20),task("B",1,10,release=.5)]
    old=run(tasks,"RA-LP-EDF"); t=run(tasks,"RA-LP-EDF-Preemption")
    assert t["metrics"]["completed_jobs"]==2
    assert t["metrics"]["preemptions"]<old["metrics"]["preemptions"]
    assert any(e["event"]=="preemption_avoided" for e in t["events"]); audit(t)


@pytest.mark.parametrize("mode",MODES)
@pytest.mark.parametrize("scenario",["S1-low","S4-spike","S5-recovery","S6-multiple","S7-overload"])
def test_seeded_modes_cache_equivalence_and_accounting(mode,scenario):
    tasks,events=workload(n=8,utilization=.85,seed=13,scenario=scenario,horizon=200)
    a=run_algorithm(tasks,events,mode,horizon=200)
    b=run_algorithm(tasks,events,mode,horizon=200,cache_budgets=False)
    for key in ("jobs","events","timeline","reservations","risk_history"): assert a[key]==b[key]
    audit(a)
    for j in a["jobs"]:
        template=next(t for t in tasks if t.task_id==j["task_id"])
        assert j["deadline"]==pytest.approx(j["release"]+template.deadline)


@pytest.mark.parametrize("mode",MODES)
def test_real_authentication_replay_and_history_cannot_be_bypassed(mode):
    from src.lab.config import preset
    from src.lab.simulation import run as lab_run
    raw=preset("Tampered and replayed"); raw["horizon"]=4
    result=lab_run(raw,mode)
    rejected=[m for m in result["security"]["messages"] if not m["gate_eligible"]]
    assert any(m["authentication"]=="failed" for m in rejected)
    assert any(m.get("replay")=="failed" for m in rejected)
    for message in rejected:
        job=next(j for j in result["trace"]["jobs"] if j["job_id"]==message["job_id"])
        assert not job["admitted"] and job["start"] is None
        assert not message["history_committed"]
    audit(result["trace"])


@pytest.mark.parametrize("mode",MODES)
def test_risk_upgrade_fails_closed_and_recovery_respects_dwell(mode):
    tasks=[task("A",8,20,True)]
    t=run(tasks,mode,events=[RiskEvent(.1,"A",1)],policy=Policy(alpha=0,ttl=100))
    assert t["metrics"]["security_compliance"]==1
    assert any(e["event"]=="safe_state" for e in t["events"])
    t=run([replace(tasks[0],exposure=.9)],mode,events=[RiskEvent(.1,"A",.1)],policy=Policy(dwell=5,ttl=100))
    assert all(e["mechanism"]=="strong" for e in t["events"] if e["event"]=="dispatch" and e["time"]<5)
    audit(t)


@pytest.mark.parametrize("mode",MODES)
def test_feasible_periodic_jobs_all_make_progress(mode):
    tasks=[replace(task(str(i),.2,3,critical=i==0),kind="periodic",period=4,release=i*.1) for i in range(4)]
    t=run(tasks,mode)
    assert t["metrics"]["completed_jobs"]==t["metrics"]["released_jobs"]==20; audit(t)


def test_reclaim_noncritical_suffix_at_fixed_point_charges_interruption_once():
    tasks=[task("normal",4,5),task("critical",2,3,True,release=.5)]
    t=run(tasks)
    critical=next(j for j in t["jobs"] if j["critical"])
    assert critical["state"]=="completed"
    outgoing=next(j for j in t["jobs"] if not j["critical"])
    assert outgoing["preemptions"]==1
    assert any(e["event"]=="preempted" and "reclaimed" in e.get("reason","") for e in t["events"])
    audit(t)


@pytest.mark.parametrize("mode",MODES)
def test_preemption_cap_and_nonpreemptible_phase_are_not_bypassed(mode):
    a=task("normal",4,10,q=4,max_preemptions=0)
    b=task("critical",1,2,True,release=.1)
    t=run([a,b],mode)
    assert t["jobs"][0]["preemptions"]==0
    assert next(j for j in t["jobs"] if j["critical"])["state"]!="completed"
    assert t["metrics"]["safe_state_events"]>=1; audit(t)


@pytest.mark.parametrize("mode",MODES)
@pytest.mark.parametrize("condition",["faulty","unavailable"])
def test_optimizer_health_gate_is_mandatory(mode,condition):
    from src.lab.config import preset
    from src.lab.simulation import run as lab_run
    raw=preset(); raw["tasks"]=raw["tasks"][:1]; raw["tasks"][0].update(kind="oneshot",health=condition)
    result=lab_run(raw,mode)
    j=result["trace"]["jobs"][0]; a=result["security"]["messages"][0]
    assert not j["admitted"] and j["start"] is None and not a["history_committed"]
    assert result["trace"]["metrics"]["security_rejected_jobs"]==1


@pytest.mark.parametrize("mode",MODES)
def test_horizon_is_release_cutoff_not_early_success(mode):
    t=run([task("late",2,5,True,release=19.9)],mode)
    assert t["jobs"][0]["finish"]>20
    assert t["jobs"][0]["finish"]<=24.9; audit(t)


def test_unexpected_spike_exposes_honest_least_cost_tradeoff():
    # The original weighted objective happens to choose strong for this small
    # chunk before the spike; least-cost light must fail-stop inside its interval.
    tasks=[task("critical",1,5,True)]
    events=[RiskEvent(.1,"critical",1)]
    old=run(tasks,"RA-LP-EDF",events)
    new=run(tasks,"RA-LP-EDF-Optimized",events)
    assert old["metrics"]["critical_completed_jobs"]==1
    assert new["metrics"]["critical_completed_jobs"]==0
    assert any(e["event"]=="security_suspension" for e in new["events"])
    assert new["metrics"]["security_compliance"]==1
