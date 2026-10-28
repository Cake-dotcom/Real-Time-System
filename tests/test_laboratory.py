from copy import deepcopy
import json
import pytest
from src.lab.config import preset, validate
from src.lab.simulation import run,compare,playback,export_json,csv_bytes
from src.security import sensor_system


def small(name="Normal operation"):
    raw=preset(name); raw["horizon"]=1.5
    for row in raw["tasks"]: row["kind"]="oneshot"
    return raw


@pytest.mark.parametrize("field,value",[("execution",0),("execution",-1),("execution",None),
    ("deadline",float('nan')),("period",float('inf')),("release",-1),("deadline",4),
    ("minimum_level",4),("minimum_level",True),("quantum",0)])
def test_invalid_editor_timing(field,value):
    raw=small(); raw["tasks"][0][field]=value
    with pytest.raises(ValueError): validate(raw)


def test_release_model_horizon_and_units():
    raw=preset(); raw["horizon"]=4
    config=validate(raw); t=config.tasks[0]
    assert t.releases(config.horizon)==[0,2000]
    assert t.deadline==1000 and t.phases[0].wcet==250
    raw["tasks"][0].update(kind="sporadic",arrivals="[0, 2, 4]")
    config=validate(raw); assert config.tasks[0].releases(config.horizon)==[0,2000]
    raw["tasks"][0]["arrivals"]="[0, 1]"
    with pytest.raises(ValueError,match="inter-arrival"): validate(raw)
    raw=small(); raw["tasks"][0]["release"]=raw["horizon"]
    assert validate(raw).tasks[0].releases(1500)==[]


def test_phase_and_event_validation():
    raw=small(); raw["tasks"][0]["phases"]='[{"execution":0.1}]'
    with pytest.raises(ValueError,match="sum"): validate(raw)
    raw=small(); raw["events"]=[dict(event_id="E1",target="unknown",type="risk_spike",time=0)]
    with pytest.raises(ValueError,match="target"): validate(raw)
    raw["events"][0].update(target="T1",time=1.5)
    with pytest.raises(ValueError,match="horizon"): validate(raw)


@pytest.mark.parametrize("field",["period","quantum"])
def test_extreme_editor_values_are_bounded_before_allocating_jobs_or_chunks(field):
    raw=preset(); raw["tasks"][0][field]=1e-12
    if field=="period": raw["tasks"][0]["deadline"]=1e-12
    with pytest.raises(ValueError,match="releases|intervals"): validate(raw)


def test_four_tasks_real_pipeline_trace_and_isolation():
    before=(dict(sensor_system.message_monitor.last_sequence),dict(sensor_system.feature_tracker.history))
    raw=small(); original=deepcopy(raw); result=run(raw)
    assert raw==original
    assert result["trace"]["metrics"]["completed_jobs"]==4
    assert all(m["authentication"]=="passed" and m["history_committed"] for m in result["security"]["messages"])
    assert before==(dict(sensor_system.message_monitor.last_sequence),dict(sensor_system.feature_tracker.history))
    trace=result["trace"]; last=0
    for interval in trace["timeline"]:
        assert interval["start"]>=last-1e-8; last=interval["end"]
        if interval["job"]:
            assert any(e["event"]=="dispatch" and e["job"]==interval["job"] and e["time"]<=interval["start"]
                       for e in trace["events"])
    for job in trace["jobs"]:
        assert job["finish"]<=job["deadline"]
        assert job["deadline"]-job["release"]==pytest.approx(next(r["deadline"]*1000 for r in raw["tasks"] if r["task_id"]==job["task_id"]))
    assert sum(sum(j["costs"].values()) for j in trace["jobs"])==pytest.approx(sum(t["end"]-t["start"] for t in trace["timeline"] if t["job"]))
    assert playback(result,len(trace["snapshots"])-1)["running"] is None
    decoded=json.loads(export_json(result))
    assert "session_id" not in export_json(result).decode()
    assert len(csv_bytes(decoded["trace"]["jobs"]))>0


@pytest.mark.parametrize("condition",["tampered","malformed","faulty","anomalous","unavailable","expired","revoked"])
def test_security_rejection_never_reaches_cpu_or_history(condition):
    raw=small(); raw["tasks"]=raw["tasks"][:1]
    if condition in {"tampered","malformed"}: raw["tasks"][0]["message"]=condition
    elif condition in {"expired","revoked"}:
        raw["events"]=[dict(event_id="E1",target="T1",type="expire_session" if condition=="expired" else "revoke_session",time=0)]
    else: raw["tasks"][0]["health"]=condition
    result=run(raw); audit=result["security"]["messages"][0]
    assert not audit["accepted"] and not audit["history_committed"]
    assert not result["trace"]["jobs"][0]["admitted"]
    assert not any(t["job"] for t in result["trace"]["timeline"])
    assert result["trace"]["metrics"]["pre_scheduler_rejections"]==1
    assert result["security"]["trusted_history_counts"]=={}
    if condition=="tampered": assert audit["authentication"]=="failed"
    if condition in {"faulty","anomalous","unavailable"}: assert audit["authentication"]=="passed"


def test_replay_uses_previously_completed_signed_message():
    raw=preset("Tampered and replayed"); raw["horizon"]=4
    result=run(raw)
    audits={m["job_id"]:m for m in result["security"]["messages"]}
    assert audits["T3:0"]["accepted"]
    replay=audits["T3:1"]
    assert replay["authentication"]=="passed" and replay["replay"]=="failed"
    assert not replay["history_committed"]
    assert result["security"]["metrics"]["replay_rejections"]==1
    assert not next(j for j in result["trace"]["jobs"] if j["job_id"]=="T3:1")["admitted"]


def test_replay_without_prior_completion_is_not_faked():
    raw=small(); raw["tasks"]=raw["tasks"][:1]; raw["tasks"][0]["message"]="replay"
    result=run(raw)
    assert result["security"]["messages"][0]["status"]=="SCENARIO_INVALID"
    assert result["security"]["metrics"]["replay_rejections"]==0


def test_risk_fail_stop_and_infeasible_critical_outcomes():
    result=run(small("Risk escalation"))
    assert any(e["event"]=="security_suspension" for e in result["trace"]["events"])
    failed=next(j for j in result["trace"]["jobs"] if j["task_id"]=="T1")
    assert failed["state"]=="failed"
    assert not next(m for m in result["security"]["messages"] if m["job_id"]==failed["job_id"])["history_committed"]
    result=run(small("Critical infeasibility"))
    assert result["trace"]["metrics"]["safe_state_events"]>0
    assert any(j["critical"] and j["state"]!="completed" for j in result["trace"]["jobs"])


def test_comparison_identity_determinism_empty_and_missing_model(monkeypatch):
    raw=small(); raw["tasks"]=raw["tasks"][:2]
    results=compare(raw,["Standard-EDF","RA-LP-EDF"])
    assert len({r["workload_id"] for r in results})==1
    repeated=run(raw)
    assert repeated["trace"]["jobs"]==results[-1]["trace"]["jobs"]
    raw["tasks"]=[]
    empty=run(raw); assert empty["trace"]["metrics"]["released_on_time_ratio"] is None
    assert playback(empty,0)["time"]==0
    from src.lab import security
    real=security.SensorHealthMonitor
    def missing():
        monitor=real(); monitor.model_bundle=None; return monitor
    monkeypatch.setattr(security,"SensorHealthMonitor",missing)
    result=run(small())
    assert result["trace"]["metrics"]["completed_jobs"]==0
    assert all(not m["gate_eligible"] for m in result["security"]["messages"])


def test_seconds_and_milliseconds_produce_identical_scheduler_trace():
    raw=small(); other=deepcopy(raw); other["time_unit"]="ms"; other["horizon"]*=1000; other["checkpoint"]*=1000
    for row in other["tasks"]:
        for field in ("release","execution","deadline","period","quantum"): row[field]*=1000
    first=run(raw); second=run(other)
    assert first["trace"]["jobs"]==second["trace"]["jobs"]
    assert first["trace"]["timeline"]==second["trace"]["timeline"]


def test_risk_duration_recovery_and_repeat_events_are_recorded_after_completion():
    raw=small(); raw["tasks"]=raw["tasks"][:1]
    raw["events"]=[dict(event_id="E",target="T1",type="risk_spike",time=.8,duration=.1,value=.9,repeat_every=.3)]
    result=run(raw)
    risk=[e for e in result["trace"]["events"] if e["event"]=="risk_event"]
    assert len(risk)==6
    assert [e["exposure"] for e in risk]==[.9,.1,.9,.1,.9,.1]
    assert result["trace"]["snapshots"][-1]["time"]==1500
    assert result["trace"]["timeline"][-1]["job"] is None


def test_missing_risk_and_gru_vehicle_domain_fail_closed():
    raw=small(); raw["tasks"]=raw["tasks"][:1]; raw["tasks"][0]["exposure"]=None
    result=run(raw)
    assert all(e["required"]==3 for e in result["trace"]["events"] if e["event"]=="dispatch")
    raw["health_backend"]="GRU"
    result=run(raw)
    assert result["trace"]["metrics"]["completed_jobs"]==0
    assert not result["security"]["messages"][0]["history_committed"]


def test_recovery_preset_obeys_dwell_and_pressure_preserves_critical_jobs():
    result=run(small("Risk recovery"))
    points=result["trace"]["risk_history"]["T1"]
    assert any(p["time"]==100 and p["value"][1]==3 for p in points)
    assert all(p["time"]>=500 for p in points if p["value"][1]==1)
    pressure=run(small("Critical pressure"))
    assert all(j["state"]=="completed" for j in pressure["trace"]["jobs"] if j["critical"])
    assert pressure["trace"]["metrics"]["ever_deferred_ratio"]>0


def test_seeded_authenticated_trial_workloads_and_paired_statistics(monkeypatch):
    from src.lab import evaluation
    first=evaluation.generated_configuration(4,.5,11,"S4-spike")
    assert first==evaluation.generated_configuration(4,.5,11,"S4-spike")
    assert first!=evaluation.generated_configuration(4,.5,22,"S4-spike")
    assert len(validate(first).tasks)==4
    # Statistics unit test isolates expensive ML execution; real runs are saved by
    # evaluate_laboratory.py, while other tests exercise the production gates.
    def deterministic_run(raw,algorithm):
        return {"workload_id":str(raw["seed"]),"trace":{"metrics":dict.fromkeys([
            "released_on_time_ratio","deadline_miss_ratio","critical_deadline_miss_ratio","security_overhead",
            "mean_residual_risk_while_executing","security_compliance","scheduler_wall_ms","pre_scheduler_rejections"],
            1 if algorithm=="RA-LP-EDF" else .5)}}
    monkeypatch.setattr(evaluation,"run",deterministic_run)
    result=evaluation.repeated(seeds=(11,22),algorithms=("Standard-EDF","RA-LP-EDF"))
    assert len(result["runs"])==4
    assert result["paired_differences"][0]["metrics"]["released_on_time_ratio"]["mean"]==.5
    assert result["summary"][0]["metrics"]["released_on_time_ratio"]["n"]==2
    with pytest.raises(ValueError,match="distinct"): evaluation.repeated(seeds=(11,11))
