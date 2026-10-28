from dataclasses import replace
import random
import pytest
from src.scheduler.model import Task, Phase, Job, generate_jobs
from src.scheduler.dynamic_risk import Policy, RiskEvent, RiskState
from src.scheduler.security_costs import default_registry, chunk_cost, total
from src.scheduler.feasibility import mps_analysis
from src.scheduler.ra_lp_edf import RALPEDF


def task(name="a", cost=2, deadline=20, **kw):
    return Task(name,(Phase("p",cost,quantum=1),),deadline,deadline,kind="oneshot",**kw)


@pytest.mark.parametrize("kw",[{"period":0},{"deadline":21},{"exposure":float('nan')},
    {"minimum_level":True},{"max_preemptions":-1},{"actual_factor":0}])
def test_invalid_task(kw):
    with pytest.raises(ValueError): replace(task(),**kw)


def test_releases_and_state_machine():
    t=replace(task(),kind="periodic",release=2,period=10,deadline=8)
    assert [j.release for j in generate_jobs([t],25)]==[2,12,22]
    s=replace(t,kind="sporadic",arrivals=(3,13,24))
    assert [j.deadline for j in generate_jobs([s],25)]==[11,21,32]
    with pytest.raises(ValueError): replace(s,arrivals=(3,12))
    with pytest.raises(ValueError): Job(t,0,2).transition("completed",2,"invalid")
    with pytest.raises(ValueError): generate_jobs([t,t],20)


def test_risk_hysteresis_upgrade_and_staleness():
    r=RiskState(task(),Policy(dwell=5,ttl=100))
    assert r.assess(0)[1]==1
    r.update(RiskEvent(1,"a",.9)); assert r.assess(1)[1]==3
    r.update(RiskEvent(2,"a",.1)); assert r.assess(2)[1]==3
    assert r.assess(6)[1]==1
    r.update(RiskEvent(7,"a",None)); assert r.assess(7)==(1,3,True)
    r.update(RiskEvent(8,"a",.1)); assert r.assess(108)==(1,3,True)


def test_cost_hand_calculation_and_fixed_point_startup():
    m=default_registry()["light"]
    assert total(chunk_cost(2,m,decision=.001))==pytest.approx(2.081)
    out=RALPEDF([task()],policy=Policy(mode="Minimum-security"),horizon=20).run()
    j=out["jobs"][0]
    assert j["state"]=="completed"
    assert j["finish"]==pytest.approx(2.122)
    assert j["costs"]["startup"]==pytest.approx(.04)
    assert sum(j["costs"].values())==pytest.approx(j["finish"])
    assert out["metrics"]["simulated_cpu_utilization"]==pytest.approx(2.122/20)
    assert out["metrics"]["response_mean"]==pytest.approx(2.122)


def test_preemption_waits_for_fixed_point_and_cap():
    a=task("a",5,20)
    b=task("b",1,4,release=.5)
    result=RALPEDF([a,b],policy=Policy(mode="Minimum-security"),horizon=20).run()
    pre=[e for e in result["events"] if e["event"]=="preempted"]
    assert pre and pre[0]["time"]==pytest.approx(1.061)
    assert all(j["state"]=="completed" for j in result["jobs"])
    result=RALPEDF([replace(a,max_preemptions=0),b],horizon=20).run()
    assert result["jobs"][0]["preemptions"]==0
    assert not any(e["event"]=="preempted" for e in result["events"])
    result=RALPEDF([replace(a,max_preemptions=0),replace(b,safety_critical=True)],horizon=20).run()
    urgent=next(j for j in result["jobs"] if j["task_id"]=="b")
    assert not urgent["admitted"]


def test_midregion_risk_spike_stops_computation_and_pays_cleanup():
    a=replace(task(cost=8),phases=(Phase("p",8,preemptible=False),))
    out=RALPEDF([a],[RiskEvent(.5,"a",1)],policy=Policy(mode="Minimum-security"),horizon=20).run()
    assert out["jobs"][0]["state"]=="failed"
    assert out["jobs"][0]["costs"]["teardown"]==pytest.approx(.02)
    assert all(t["end"]<=.5+1e-9 for t in out["timeline"] if t.get("mechanism")=="light")
    assert out["metrics"]["security_compliance"]==1


def test_unavailable_protection_critical_infeasibility_and_overrun():
    a=replace(task(exposure=1,safety_critical=True),phases=(Phase("p",2,mechanisms=("light",)),))
    out=RALPEDF([a],horizon=20).run()
    assert out["jobs"][0]["state"]=="rejected"
    assert out["metrics"]["safe_state_events"]==1
    out=RALPEDF([task(actual_factor=1.2)],horizon=20).run()
    assert out["jobs"][0]["state"]=="failed"
    assert any(e["event"]=="budget_overrun" for e in out["events"])


def test_critical_reservation_and_noncritical_deferral():
    out=RALPEDF([task("critical",3,6,safety_critical=True),task("low",4,6)],horizon=10).run()
    assert out["jobs"][0]["state"]=="completed"
    assert any(e["event"]=="deferred" for e in out["events"])
    assert out["reservations"]
    assert out["metrics"]["reservation_violations"]==0


def test_static_analysis_known_cases():
    a=task("a",1,10); b=task("b",2,20)
    choices={(t.task_id,"p"):"light" for t in [a,b]}
    assert mps_analysis([a,b],default_registry(),choices)["status"]=="feasible"
    a=task("a",11,10)
    assert mps_analysis([a],default_registry(),{("a","p"):"light"})["status"]=="infeasible"
    assert mps_analysis([b],default_registry(),choices,max_points=0)["status"]=="unknown"


def test_empty_metrics():
    out=RALPEDF([],horizon=20).run()["metrics"]
    assert out["deadline_miss_ratio"] is None
    assert out["security_compliance"] is None
    assert out["idle_time"]==20


def test_resume_cost_survives_deferral_and_recovery():
    sim=RALPEDF([task()],policy=Policy(mode="Minimum-security"),horizon=20)
    job=sim.jobs[0]
    job.transition("pending",0,"release"); job.transition("ready",0,"admit"); job.admitted=True
    job.transition("preempted",0,"context saved"); job.needs_resume=True
    job.transition("deferred",0,"capacity reclaimed"); job.transition("ready",0,"recovered")
    sim.dispatch()
    assert sim.block["costs"]["resume"]==pytest.approx(.02)
    assert not job.needs_resume


def test_static_fixed_point_count_matches_hand_example_and_trace():
    # With q=0: at L=3, short-task demand=1, slack=2, so split c=4 in two.
    tasks=[replace(task("short",1,3),kind="periodic"),replace(task("long",4,10),kind="periodic")]
    registry=default_registry(0)
    analysis=mps_analysis(tasks,registry,{(t.task_id,"p"):"strong" for t in tasks})
    assert analysis["status"]=="feasible" and analysis["counts"]["long"]==[2]
    tasks=[replace(t,phases=(replace(t.phases[0],quantum=t.phases[0].wcet/analysis["counts"][t.task_id][0]),)) for t in tasks]
    out=RALPEDF(tasks,registry=registry,policy=Policy(mode="Static-Sec-EDF",decision_cost=0,admission=False,overload=False),horizon=30).run()
    assert all(j["state"]=="completed" for j in out["jobs"])
    assert out["metrics"]["preemptions"]>0


def test_upgrade_at_fixed_point_overrides_dwell():
    out=RALPEDF([task(cost=3)],[RiskEvent(1.061,"a",1)],
        policy=Policy(mode="Minimum-security",dwell=100),horizon=20).run()
    dispatches=[e for e in out["events"] if e["event"]=="dispatch"]
    assert dispatches[0]["mechanism"]=="light"
    assert dispatches[1]["mechanism"]=="strong"
    assert out["jobs"][0]["state"]=="completed"
    assert out["metrics"]["mechanism_switches"]==1


def test_three_phases_and_no_double_charged_current_interval():
    phases=tuple(Phase(str(i),1,quantum=1) for i in range(3))
    a=replace(task(),phases=phases,safety_critical=True)
    events=[RiskEvent(t,"a",.1) for t in [.2,.3,.4,.5,.6]]
    out=RALPEDF([a],events,policy=Policy(mode="Minimum-security"),horizon=20).run()
    j=out["jobs"][0]
    assert j["finish"]==pytest.approx(3*1.061)
    assert j["costs"]["base"]==pytest.approx(3)
    assert j["costs"]["startup"]==pytest.approx(.06)
    assert out["metrics"]["reservation_violations"]==0


def test_early_finish_can_recover_deferred_work():
    # Admission uses full budgets, but early completion frees reserved capacity.
    out=RALPEDF([task("critical",3,6,safety_critical=True,actual_factor=.2),
                task("low",4,6,actual_factor=.2)],horizon=10).run()
    assert any(e["event"]=="deferred" for e in out["events"])
    assert all(j["state"]=="completed" for j in out["jobs"])
    assert out["metrics"]["overload_recovery_durations"]


def test_seeded_workload_reproducibility_and_paired_algorithms():
    from dataclasses import asdict
    from src.scheduler.experiments import workload, run_algorithm, ALGORITHMS, digest
    first=workload(n=4,seed=17,horizon=40)
    second=workload(n=4,seed=17,horizon=40)
    assert first==second
    before=digest([asdict(t) for t in first[0]])
    for mode in ALGORITHMS:
        out=run_algorithm(*first,mode,horizon=40)
        assert out["metrics"]["released_jobs"]==4
        assert out["metrics"]["security_compliance"] in (1,None)
        assert digest([asdict(t) for t in first[0]])==before


def test_constant_low_scenario_does_not_expire_during_final_job_drain():
    from src.scheduler.experiments import run_algorithm
    late=task("late",10,100,release=395)
    out=run_algorithm([late],[],"RA-LP-EDF",horizon=400)
    assert out["jobs"][0]["state"]=="completed"
    assert all(point["value"]==(.1,1,False) for point in out["risk_history"]["late"])


@pytest.mark.parametrize("seed",range(20))
def test_randomized_accounting_security_and_deadline_invariants(seed):
    rng=random.Random(seed)
    tasks=[task(str(i),rng.uniform(.1,3),rng.randint(8,20),release=rng.uniform(0,3),
                exposure=rng.random(),safety_critical=i==0) for i in range(5)]
    out=RALPEDF(tasks,[RiskEvent(4,"1",1)],horizon=25).run()
    for j in out["jobs"]:
        if j["state"]=="completed": assert j["finish"]<=j["deadline"]+1e-8
        assert j["preemptions"]<=100
        assert all(v>=-1e-8 for v in j["costs"].values())
    busy=sum(t["end"]-t["start"] for t in out["timeline"] if t["job"])
    assert busy==pytest.approx(sum(sum(j["costs"].values()) for j in out["jobs"]))
    assert out["metrics"]["security_compliance"] in (1,None)
    assert out["metrics"]["reservation_violations"]==0
