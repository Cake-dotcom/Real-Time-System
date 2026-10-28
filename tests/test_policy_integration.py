"""Exercise the production coordinator, not just standalone policy selection."""
import copy
from unittest.mock import Mock

import pytest

from src.security import sensor_system as system
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor
from src.security.risk_policy import select_validation_policy, RISK_MATRIX
from src.ml.train_sensor_model import FEATURES
from session_helpers import sign_for_monitor
from src.security.source_sessions import SIMULATED_HANDSHAKE_COST


class NormalModel:
    def predict(self, frame):
        return ["normal"] * len(frame)


@pytest.fixture(autouse=True)
def isolated_system(monkeypatch):
    health = SensorHealthMonitor()
    health.model_bundle = {"model": NormalModel(), "features": FEATURES}
    monkeypatch.setattr(system, "message_monitor", MessageMonitor(system.SENSOR_KEYS))
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    monkeypatch.setattr(system, "health_monitor", health)


def item(sensor="LIDAR_01", sequence=1, reading=12.0, deadline=10):
    message = {"sensor_id": sensor, "sequence": sequence,
               "timestamp": 1000 + sequence, "distance_m": reading}
    message, mac = sign_for_monitor(system.message_monitor, message)
    return {"message": message, "mac": mac,
            "arrival_time": 0, "execution_time": 3, "security_overhead": 1,
            "deadline": deadline, "message_age_ms": 5.0}


def histories():
    return copy.deepcopy((dict(system.feature_tracker.history),
                          system.feature_tracker.last_sequence,
                          system.health_monitor.last_distance))


@pytest.mark.parametrize("attack", ["none", "mac", "replay", "infeasible"])
def test_ra_scheduler_is_after_real_rf_security_gates(monkeypatch, attack):
    from src.scheduler import sensor_adapter
    candidate=item("CAMERA_01",deadline=40)
    schedule=Mock(wraps=sensor_adapter.schedule_sensor_tasks)
    monkeypatch.setattr(sensor_adapter,"schedule_sensor_tasks",schedule)
    if attack=="replay":
        assert system.process_messages([candidate],scheduling_algorithm="RA-LP-EDF")["messages"][0]["accepted"]
        schedule.reset_mock()
    if attack=="mac": candidate["message"]["distance_m"]=999
    if attack=="infeasible": candidate["deadline"]=1
    before=histories()
    result=system.process_messages([candidate],scheduling_algorithm="RA-LP-EDF")
    if attack=="none":
        assert result["messages"][0]["accepted"]
        schedule.assert_called_once()
        assert result["schedule"]["research"]["jobs"][0]["state"]=="completed"
        assert result["schedule"]["research"]["jobs"][0]["costs"]["mandatory_validation"]==pytest.approx(result["messages"][0]["total_security_overhead"])
    else:
        assert not result["messages"][0]["accepted"]
        assert histories()==before
        if attack in {"mac","replay"}: schedule.assert_not_called()


@pytest.mark.parametrize("sensor,level,checks,cost", [
    ("CAMERA_01", "low", {"reading_plausibility"}, 0),
    ("LIDAR_01", "medium", {"reading_plausibility", "temporal_consistency"}, 1),
])
def test_real_policy_selects_and_executes_checks(sensor, level, checks, cost):
    result = system.process_messages([item(sensor)])
    decision = result["messages"][0]
    assert decision["accepted"]
    assert decision["policy"]["risk_level"] == level
    assert decision["policy"]["framework"].startswith("NIST SP 800-30")
    assert set(decision["additional_checks"]["checks"]) == checks
    assert all(c["passed"] for c in decision["additional_checks"]["checks"].values())
    assert result["schedule"]["results"][0]["finish"] == 4 + cost + SIMULATED_HANDSHAKE_COST
    assert list(system.feature_tracker.history[sensor]) == [12.0]


@pytest.mark.parametrize("attack", ["mac", "replay"])
def test_permissive_policy_cannot_bypass_security_gates(monkeypatch, attack):
    candidate = item("CAMERA_01")  # Actual normal evidence yields low risk.
    if attack == "replay":
        assert system.process_messages([candidate])["messages"][0]["accepted"]
    else:
        candidate["message"]["distance_m"] = 13.0
    before = histories()
    replay_before = dict(system.message_monitor.last_sequence)
    policy = Mock(return_value=select_validation_policy("low"))
    checks = Mock(return_value={"passed": True, "checks": {}})
    schedule = Mock()
    monkeypatch.setattr(system, "assess_sensor_risk", policy)
    monkeypatch.setattr(system, "validate_additional_checks", checks)
    monkeypatch.setattr(system, "schedule_message_tasks", schedule)
    result = system.process_messages([candidate])["messages"][0]
    assert result["status"] == "SECURITY_ALERT"
    assert not result["accepted"]
    assert result["policy"] is None
    assert result["authentication"] == ("failed" if attack == "mac" else "passed")
    assert result["replay"] == ("not_evaluated" if attack == "mac" else "failed")
    policy.assert_not_called()
    checks.assert_not_called()
    schedule.assert_not_called()
    assert histories() == before
    assert system.message_monitor.last_sequence == replay_before


def test_high_risk_executes_enhanced_checks_and_retains_health_rejection():
    assert system.process_messages([item()])["messages"][0]["accepted"]
    before = histories()
    result = system.process_messages([item(sequence=2, reading=40)])["messages"][0]
    assert result["policy"]["matrix_risk"] == "high"
    assert set(result["additional_checks"]["checks"]) == {
        "temporal_consistency", "reading_plausibility", "stability_check"}
    assert not result["additional_checks"]["checks"]["temporal_consistency"]["passed"]
    assert not result["accepted"]
    assert histories() == before


def test_failed_check_blocks_healthy_model_prediction():
    # Stable low-variance history gives a large z-score for a small change;
    # the existing sudden-change health rule does not reject this reading.
    for sequence, reading in enumerate([12.0, 12.1], 1):
        message = item(sequence=sequence, reading=reading)["message"]
        system.feature_tracker.commit_reading(message)
        system.health_monitor.commit_reading(message)
    before = histories()
    result = system.process_messages([item(sequence=3, reading=13.0)])["messages"][0]
    assert result["health"]["healthy"]
    assert result["status"] == "POLICY_REJECTED"
    assert not result["accepted"]
    assert histories() == before


def test_successful_extra_checks_cannot_rehabilitate_unhealthy_reading():
    system.health_monitor.model_bundle["model"].predict = lambda frame: ["anomalous_reading"]
    result = system.process_messages([item("CAMERA_01")])["messages"][0]
    assert result["additional_checks"]["passed"]
    assert result["policy"]["response"] == "reject"
    assert result["status"] == "SENSOR_FAULT"
    assert not result["accepted"]
    assert histories() == ({}, {}, {})


@pytest.mark.parametrize("mode", ["missing_model", "unknown_prediction", "missing_feature", "inference_error"])
def test_unknown_evidence_fails_closed(mode, monkeypatch):
    if mode == "missing_model":
        system.health_monitor.model_bundle = None
    elif mode == "unknown_prediction":
        system.health_monitor.model_bundle["model"].predict = lambda frame: ["unrecognized"]
    elif mode == "missing_feature":
        build = system.feature_tracker.build_features
        def incomplete(**kwargs):
            features = build(**kwargs)
            del features["reading_delta"]
            return features
        monkeypatch.setattr(system.feature_tracker, "build_features", incomplete)
    else:
        system.health_monitor.model_bundle["model"].predict = Mock(side_effect=ValueError("unavailable"))
    before = histories()
    result = system.process_messages([item()])["messages"][0]
    assert result["status"] == "POLICY_UNAVAILABLE"
    assert not result["accepted"]
    assert result["policy"]["response"] == "defer"
    assert histories() == before


def test_policy_cost_causes_deadline_miss_exactly_once():
    before = histories()
    result = system.process_messages([item(deadline=4)])
    decision = result["messages"][0]
    assert decision["simulated_extra_cost"] == 1
    assert decision["total_security_overhead"] == 2 + SIMULATED_HANDSHAKE_COST
    assert result["schedule"]["results"][0]["finish"] == 5 + SIMULATED_HANDSHAKE_COST
    assert decision["status"] == "DEADLINE_MISSED"
    assert not decision["accepted"]
    assert histories() == before


def test_fallback_defers_noncritical_without_history_commit():
    result = system.process_messages([item(deadline=7), item("CAMERA_01", deadline=8)])
    assert result["schedule"]["mode"] == "CRITICAL_ONLY"
    assert result["messages"][0]["accepted"]
    assert result["messages"][1]["status"] == "DEFERRED"
    assert "CAMERA_01" not in system.feature_tracker.history
    assert "CAMERA_01" not in system.health_monitor.last_distance


@pytest.mark.parametrize("reading", [True, None, "12", float("nan"), float("inf"), -1, 201])
def test_malformed_readings_never_reach_policy(reading, monkeypatch):
    policy = Mock()
    monkeypatch.setattr(system, "assess_sensor_risk", policy)
    before = histories()
    assert not system.process_messages([item(reading=reading)])["messages"][0]["accepted"]
    policy.assert_not_called()
    assert histories() == before


@pytest.mark.parametrize("bad", [None, {}, {"message": []}, {"message": {"sensor_id": []}}])
def test_malformed_envelope_fails_closed(bad):
    assert not system.process_messages([bad])["messages"][0]["accepted"]


@pytest.mark.parametrize("field,value", [("security_overhead", -1), ("execution_time", float("nan")),
                                         ("deadline", True), ("arrival_time", float("inf"))])
def test_invalid_timing_fails_closed(field, value):
    candidate = item()
    candidate[field] = value
    assert system.process_messages([candidate])["messages"][0]["status"] == "INVALID_INPUT"


def test_nist_table_i2_cells():
    # Independently transcribed expected rows, low -> high impact.
    assert list(RISK_MATRIX.values()) == [
        ("very_low", "very_low", "very_low", "low", "low"),
        ("very_low", "low", "low", "low", "moderate"),
        ("very_low", "low", "moderate", "moderate", "high"),
        ("very_low", "low", "moderate", "high", "very_high"),
        ("very_low", "low", "moderate", "high", "very_high"),
    ]


def test_placeholder_is_not_security_evidence():
    from src.security.additional_validation import validate_additional_checks
    assert not validate_additional_checks({}, ("mandatory_sensor_checks",))["passed"]


def test_legacy_login_risk_and_mfa_still_work():
    from src.security.risk_engine import RiskEngine
    from src.security.auth_policy import choose_auth_action
    event = {"failed_attempts_last_5min": 35, "login_attempts_last_1min": 25,
             "unique_accounts_targeted": 2, "time_since_last_login_seconds": 20,
             "unusual_login_time": 1, "new_ip_for_user": 1, "successful_login": 0}
    risk = RiskEngine().assess(event)
    assert risk["risk_level"] in {"low", "medium", "high", "critical"}
    assert choose_auth_action(risk["risk_level"], 35)["action"] == "temporary_block"
    from src.security.security_system import evaluate_login
    result = evaluate_login(event)
    assert result["security_action"]["action"] == "temporary_block"
    assert result["schedule"]["results"][0]["deadline_met"]
