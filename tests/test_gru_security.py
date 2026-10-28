import copy
import numpy as np
import pytest
from test_gru_model import artifact
from src.ml.gru_sensor_model import FEATURES
from src.security import sensor_system as system
from src.security.gru_health import GRUHealthMonitor
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.source_sessions import authenticate_sender


@pytest.fixture
def ready(artifact, monkeypatch):
    monitor = MessageMonitor(system.SENSOR_KEYS)
    health = GRUHealthMonitor(artifact)
    monkeypatch.setattr(system, "message_monitor", monitor)
    monkeypatch.setattr(system, "health_monitor", health)
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    sender = authenticate_sender(monitor.sessions, "SKAB_01", system.SENSOR_KEYS["SKAB_01"])
    records = [{"sensor_id": "SKAB_01", "sensor_domain": "SKAB", "recording_id": "run-a",
                "timestamp": 100 + i, "sensor_values": dict.fromkeys(FEATURES, 2.)} for i in range(4)]
    health.commission_trusted_history("SKAB_01", sender.session_id, "run-a", records[:3])
    message, mac = sender.sign({**records[-1], "sequence": 1, "distance_m": 12.})
    item = {"message": message, "mac": mac, "arrival_time": 0, "execution_time": 1,
            "security_overhead": 1, "deadline": 20, "message_age_ms": 0}
    return health, sender, item


def test_valid_gru_passes_and_commits_only_after_gates(ready):
    health, sender, item = ready
    result = system.process_messages([item])["messages"][0]
    assert result["accepted"] and result["health"]["sequence_ready"]
    assert result["health"]["dataset_prediction"] == "normal"
    assert health.history["SKAB_01"][-1][0] == 103
    assert result["total_security_overhead"] == 1 + result["simulated_extra_cost"] + result["simulated_handshake_cost"]
    message, mac = sender.sign({**item["message"], "timestamp": 104, "sequence": 2})
    reused = system.process_messages([{**item, "message": message, "mac": mac}])["messages"][0]
    assert reused["accepted"] and reused["session_reused"]
    assert system.message_monitor.sessions.metrics["mac_verifications"] == 2


@pytest.mark.parametrize("failure",["none","mac","replay","missing","late","revoked"])
def test_ra_adapter_preserves_gru_authentication_and_history(ready, failure):
    health,sender,item=ready
    if failure=="replay":
        assert system.process_messages([item],scheduling_algorithm="RA-LP-EDF")["messages"][0]["accepted"]
    before=copy.deepcopy(list(health.history["SKAB_01"]))
    if failure=="mac": item["message"]["sensor_values"][FEATURES[0]]=999
    if failure=="missing": health.predictor=None
    if failure=="late": item["deadline"]=1
    if failure=="revoked": system.message_monitor.sessions.revoke_session("SKAB_01")
    result=system.process_messages([item],scheduling_algorithm="RA-LP-EDF")
    assert result["messages"][0]["accepted"] == (failure=="none")
    if failure!="none": assert list(health.history["SKAB_01"])==before
    else: assert result["schedule"]["algorithm"]=="RA-LP-EDF"


@pytest.mark.parametrize("failure", ["mac", "unknown", "late", "anomaly", "missing", "exception", "unknown_prediction", "malformed", "domain", "short", "new_run", "expired", "revoked"])
def test_failures_never_commit_history(ready, failure, monkeypatch):
    health, sender, item = ready
    before = copy.deepcopy(list(health.history["SKAB_01"]))
    if failure == "mac": item["message"]["sensor_values"][FEATURES[0]] = 999
    elif failure == "unknown": item["message"]["sensor_id"] = "UNKNOWN"
    elif failure == "late":
        item["deadline"] = 0
        monkeypatch.setattr(system, "CRITICAL_SENSORS", system.CRITICAL_SENSORS | {"SKAB_01"})
    elif failure == "missing": health.predictor = None
    elif failure == "anomaly":
        monkeypatch.setattr(health.predictor, "predict", lambda *_: {"prediction": "anomalous", "anomaly_score": .9})
    elif failure == "unknown_prediction":
        monkeypatch.setattr(health.predictor, "predict", lambda *_: {"prediction": "surprise", "anomaly_score": .9})
    elif failure == "exception":
        def fail(*_): raise RuntimeError("model error")
        monkeypatch.setattr(health.predictor, "predict", fail)
    elif failure == "short": health.history["SKAB_01"].clear(); before = []
    elif failure == "expired": system.message_monitor.sessions.clock = lambda: 1e20
    elif failure == "revoked": system.message_monitor.sessions.revoke_session("SKAB_01")
    else:
        msg = copy.deepcopy(item["message"])
        if failure == "malformed": msg["sensor_values"][FEATURES[0]] = None
        if failure == "domain": msg.pop("sensor_values")
        if failure == "new_run": msg["recording_id"] = "run-b"
        item["message"], item["mac"] = sender.sign(msg)
    result = system.process_messages([item])["messages"][0]
    assert not result["accepted"]
    assert not system.feature_tracker.history and not health.last_distance
    if failure == "new_run": assert not health.history
    else: assert list(health.history["SKAB_01"]) == before
    if failure in ["mac", "unknown", "expired", "revoked"]:
        assert "health" not in result
    if failure == "anomaly":
        assert result["status"] == "SENSOR_FAULT"
        assert result["additional_checks"]["passed"]
    if failure == "late": assert result["status"] == "DEADLINE_MISSED"


def test_replay_and_session_reset(ready):
    health, _, item = ready
    assert system.process_messages([item])["messages"][0]["accepted"]
    before = copy.deepcopy(list(health.history["SKAB_01"]))
    replay = system.process_messages([item])["messages"][0]
    assert replay["status"] == "SECURITY_ALERT" and replay["replay"] == "failed"
    assert list(health.history["SKAB_01"]) == before
    sender = authenticate_sender(system.message_monitor.sessions, "SKAB_01", system.SENSOR_KEYS["SKAB_01"])
    message, mac = sender.sign({**item["message"], "sequence": 2, "timestamp": 104})
    result = system.process_messages([{**item, "message": message, "mac": mac}])["messages"][0]
    assert not result["accepted"] and not health.history


def test_missing_artifact_and_cross_sensor_history(ready, tmp_path):
    health, sender, item = ready
    empty = GRUHealthMonitor(tmp_path / "absent.pt")
    assert not empty.check(item["message"])["healthy"]
    message = {**item["message"], "sensor_id": "RADAR_01"}
    health.bind_session(message)
    assert not health.check(message)["healthy"]
    assert len(health.history["SKAB_01"]) == 3


def test_commissioning_rejects_wrong_group(ready):
    health, sender, item = ready
    with pytest.raises(ValueError):
        health.commission_trusted_history("SKAB_01", sender.session_id, "other-run", [item["message"]] * 3)


def test_session_reuse_never_skips_mac(ready):
    health, sender, item = ready
    assert system.process_messages([item])["messages"][0]["accepted"]
    before = copy.deepcopy(list(health.history["SKAB_01"]))
    message, mac = sender.sign({**item["message"], "sequence": 2, "timestamp": 104})
    message["sensor_values"] = dict.fromkeys(FEATURES, 999.)
    rejected = system.process_messages([{**item, "message": message, "mac": mac}])["messages"][0]
    assert rejected["reason"] == "Invalid MAC" and "health" not in rejected
    assert system.message_monitor.sessions.metrics["mac_verifications"] == 2
    assert list(health.history["SKAB_01"]) == before


def test_batch_time_reversal_rejected(ready):
    health, sender, item = ready
    first, mac1 = sender.sign({**item["message"], "timestamp": 104})
    second, mac2 = sender.sign({**item["message"], "timestamp": 103, "sequence": 2})
    result = system.process_messages([{**item, "message": first, "mac": mac1},
                                      {**item, "message": second, "mac": mac2}])
    assert result["messages"][0]["accepted"]
    assert result["messages"][1]["status"] == "INVALID_INPUT"
    assert health.history["SKAB_01"][-1][0] == 104


def test_malformed_run_and_batch_run_change_fail_safely(ready):
    health, sender, item = ready
    second, mac = sender.sign({**item["message"], "recording_id": "run-b", "sequence": 2, "timestamp": 104})
    result = system.process_messages([item, {**item, "message": second, "mac": mac}])
    assert result["messages"][0]["accepted"]
    assert result["messages"][1]["status"] == "INVALID_INPUT"
    bad, mac = sender.sign({**item["message"], "recording_id": [], "sequence": 3, "timestamp": 104})
    result = system.process_messages([{**item, "message": bad, "mac": mac}])
    assert not result["messages"][0]["accepted"]
