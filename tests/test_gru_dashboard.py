import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_gru_model import artifact
from src.security import sensor_system as system
from src.security.gru_health import GRUHealthMonitor
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker


def configure(monkeypatch, path):
    monkeypatch.setattr(system, "health_monitor", GRUHealthMonitor(path))
    monkeypatch.setattr(system, "message_monitor", MessageMonitor(system.SENSOR_KEYS))
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    return AppTest.from_file(Path(__file__).resolve().parents[1] / "src/dashboard/app.py", default_timeout=30).run()


def test_gru_dashboard_fails_closed_for_vehicle_and_shows_model(artifact, monkeypatch):
    app = configure(monkeypatch, artifact)
    assert not app.exception
    assert any("Active sensor-health model: GRU" in element.value for element in app.markdown)
    next(b for b in app.button if b.label == "Process Sensor Message").click().run()
    assert not app.exception
    decision = json.loads(app.json[0].value)
    assert not decision["accepted"] and decision["status"] == "POLICY_UNAVAILABLE"
    assert decision["health"]["anomaly_score"] is None


def test_gru_dashboard_missing_artifact_is_usable(tmp_path, monkeypatch):
    app = configure(monkeypatch, tmp_path / "missing.pt")
    assert not app.exception
    next(b for b in app.button if b.label == "Process Sensor Message").click().run()
    assert not app.exception
    assert not json.loads(app.json[0].value)["accepted"]
