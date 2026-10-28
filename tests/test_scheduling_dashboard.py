from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.security import sensor_system as system
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor


def test_live_ra_dashboard_and_real_experiment_trace(monkeypatch):
    monkeypatch.setattr(system,"message_monitor",MessageMonitor(system.SENSOR_KEYS))
    monkeypatch.setattr(system,"feature_tracker",SensorFeatureTracker())
    monkeypatch.setattr(system,"health_monitor",SensorHealthMonitor())
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"src/dashboard/app.py",default_timeout=30).run()
    next(c for c in app.selectbox if c.label=="Live scheduling algorithm").select("RA-LP-EDF")
    next(b for b in app.button if b.label=="Process Sensor Message").click().run()
    assert not app.exception
    assert any("released_jobs" in t.value.columns for t in app.dataframe)
    next(b for b in app.button if b.label=="Run scheduling experiment").click().run()
    assert not app.exception
    trace=app.session_state["scheduling_trace"]
    assert trace["algorithm"]=="RA-LP-EDF" and trace["timeline"]
    assert trace["metrics"]["released_jobs"]>8
