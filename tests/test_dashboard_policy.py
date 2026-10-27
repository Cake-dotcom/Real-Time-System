import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from src.security import sensor_system as system
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor


@pytest.mark.parametrize("scenario,expected", [
    ("Valid message", ["NORMAL"]),
    ("Tampered message", ["SECURITY_ALERT"]),
    ("Replay previous message", ["NORMAL", "SECURITY_ALERT"]),
])
def test_dashboard_runs_backend_and_displays_actual_policy(monkeypatch, scenario, expected):
    monkeypatch.setattr(system, "message_monitor", MessageMonitor(system.SENSOR_KEYS))
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    monkeypatch.setattr(system, "health_monitor", SensorHealthMonitor())
    captured = []
    process = system.process_messages
    def record(messages):
        result = process(messages)
        captured.append(result)
        return result
    monkeypatch.setattr(system, "process_messages", record)
    policy = Mock(wraps=system.assess_sensor_risk)
    monkeypatch.setattr(system, "assess_sensor_risk", policy)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "src/dashboard/app.py",
                            default_timeout=30).run()
    assert not app.exception
    next(control for control in app.selectbox if control.label == "Simulation mode").select(scenario)
    next(button for button in app.button if button.label == "Process Sensor Message").click().run()
    assert not app.exception
    decisions = captured[-1]["messages"]
    assert [d["status"] for d in decisions] == expected
    shown = [json.loads(element.value) for element in app.json]
    assert shown == json.loads(json.dumps(decisions))
    assert policy.call_count == (0 if scenario == "Tampered message" else 1)
    assert all(not d["accepted"] for d in decisions if d["status"] == "SECURITY_ALERT")
    assert decisions[0]["source_authentication"] == "passed"
    metrics = next(table.value for table in app.dataframe if "full_handshakes" in table.value.columns)
    assert metrics.iloc[0]["full_handshakes"] == system.message_monitor.sessions.metrics["full_handshakes"]


@pytest.mark.parametrize("lifecycle", ["reuse", "expired", "revoked"])
def test_dashboard_session_lifecycle_uses_backend(monkeypatch, lifecycle):
    monitor = MessageMonitor(system.SENSOR_KEYS)
    monkeypatch.setattr(system, "message_monitor", monitor)
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    monkeypatch.setattr(system, "health_monitor", SensorHealthMonitor())
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "src/dashboard/app.py",
                            default_timeout=30).run()
    submit = lambda: next(b for b in app.button if b.label == "Process Sensor Message").click().run()
    submit()
    assert json.loads(app.json[0].value)["accepted"]
    if lifecycle == "expired":
        future = monitor.sessions.now() + 61
        monitor.sessions.clock = lambda: future
    elif lifecycle == "revoked":
        next(b for b in app.button if b.label == "Revoke source session").click().run()
    next(c for c in app.number_input if c.label == "Sequence number").set_value(2)
    submit()
    assert not app.exception
    result = json.loads(app.json[0].value)
    if lifecycle == "reuse":
        assert result["accepted"] and result["session_reused"]
        assert monitor.sessions.metrics["full_handshakes"] == 1
    else:
        assert not result["accepted"] and result["source_authentication"] == "failed"
        assert lifecycle in result["reason"]
        next(b for b in app.button if b.label == "Authenticate / reauthenticate source").click().run()
        submit()
        assert not app.exception
        assert json.loads(app.json[0].value)["accepted"]
        assert monitor.sessions.metrics["full_handshakes"] == 2
