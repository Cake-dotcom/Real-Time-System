
import copy

import pytest

from src.security import sensor_system
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor
from session_helpers import sign_for_monitor


@pytest.fixture(autouse=True)
def reset_monitors():
    """Give each test independent authentication, health, and feature state."""
    sensor_system.message_monitor = MessageMonitor(
        sensor_system.SENSOR_KEYS
    )
    sensor_system.health_monitor = SensorHealthMonitor(
        max_distance_change=20.0
    )
    sensor_system.feature_tracker = SensorFeatureTracker()


def make_message(
    sensor_id="LIDAR_01",
    sequence=1,
    distance=12.0,
    arrival=0,
    execution=3,
    overhead=1,
    deadline=10,
):
    message = {
        "sensor_id": sensor_id,
        "sequence": sequence,
        "timestamp": 1000 + sequence,
        "distance_m": distance,
    }

    message, mac = sign_for_monitor(sensor_system.message_monitor, message)
    return {
        "message": message,
        "mac": mac,
        "arrival_time": arrival,
        "execution_time": execution,
        "security_overhead": overhead,
        "deadline": deadline,
    }


def test_valid_message_is_accepted():
    result = sensor_system.process_messages([
        make_message()
    ])

    assert result["messages"][0]["status"] == "NORMAL"
    assert result["messages"][0]["accepted"] is True
    assert result["schedule"]["mode"] == "ALL_SENSORS"


def test_tampered_message_is_rejected():
    item = make_message()
    item["message"]["distance_m"] = 13.0

    result = sensor_system.process_messages([item])

    assert result["messages"][0]["status"] == "SECURITY_ALERT"
    assert result["messages"][0]["accepted"] is False
    assert result["messages"][0]["reason"] == "Invalid MAC"


def test_replayed_message_is_rejected():
    item = make_message()

    result = sensor_system.process_messages([
        item,
        copy.deepcopy(item),
    ])

    assert result["messages"][0]["accepted"] is True
    assert result["messages"][1]["status"] == "SECURITY_ALERT"
    assert "Replay" in result["messages"][1]["reason"]


def test_out_of_range_sensor_reading_is_rejected():
    result = sensor_system.process_messages([
        make_message(distance=250.0)
    ])

    assert result["messages"][0]["status"] == "SENSOR_FAULT"
    assert result["messages"][0]["accepted"] is False
    assert (
        "Distance outside valid range"
        in result["messages"][0]["reason"]
    )


def test_deadline_miss_is_not_accepted():
    result = sensor_system.process_messages([
        make_message(
            execution=10,
            overhead=2,
            deadline=5,
        )
    ])

    assert result["schedule"]["mode"] == "CRITICAL_DEADLINE_FAILURE"
    assert result["messages"][0]["status"] == "DEADLINE_MISSED"
    assert result["messages"][0]["accepted"] is False


def test_unknown_sensor_is_rejected():
    message = {
        "sensor_id": "UNKNOWN_SENSOR",
        "sequence": 1,
        "timestamp": 1001,
        "distance_m": 12.0,
    }

    result = sensor_system.process_messages([
        {
            "message": message,
            "mac": "invalid",
            "arrival_time": 0,
            "execution_time": 3,
            "security_overhead": 1,
            "deadline": 10,
        }
    ])

    assert result["messages"][0]["status"] == "SECURITY_ALERT"
    assert result["messages"][0]["accepted"] is False
    assert result["messages"][0]["reason"] == "Unknown sensor"


def test_ml_anomalous_prediction_is_rejected():
    """Verify that an anomalous ML prediction blocks message acceptance."""

    class AlwaysAnomalousModel:
        def predict(self, features):
            return ["anomalous_reading"]

    expected_features = [
        "sensor_criticality",
        "seq_delta",
        "message_age_ms",
        "reading",
        "reading_delta",
        "reading_zscore",
        "reading_std_last20",
        "identical_reading_streak",
        "mac_verified",
        "sensor_type",
        "reading_unit",
    ]

    sensor_system.health_monitor.model_bundle = {
        "model": AlwaysAnomalousModel(),
        "features": expected_features,
        "target": "sensor_health_label",
        "classes": ["anomalous_reading", "faulty", "normal"],
    }

    result = sensor_system.process_messages([
        make_message()
    ])

    message_result = result["messages"][0]

    assert message_result["status"] == "SENSOR_FAULT"
    assert message_result["accepted"] is False
    assert message_result["ml_prediction"] == "anomalous_reading"
    assert message_result["risk_level"] == "high"
    assert "ML model classified reading as anomalous" in (
        message_result["reason"]
    )
    assert result["schedule"]["mode"] == "NO_VALID_TASKS"


def test_invalid_mac_does_not_update_feature_history():
    """Unauthenticated data must not enter the sensor feature history."""

    item = make_message()
    item["message"]["distance_m"] = 99.0  # MAC is now invalid.

    result = sensor_system.process_messages([item])

    assert result["messages"][0]["status"] == "SECURITY_ALERT"
    assert list(
        sensor_system.feature_tracker.history["LIDAR_01"]
    ) == []
    assert "LIDAR_01" not in sensor_system.feature_tracker.last_sequence

def test_anomalous_reading_does_not_update_either_history():
    """An ML-rejected reading must not contaminate either history."""

    class AlwaysAnomalousModel:
        def predict(self, features):
            return ["anomalous_reading"]

    sensor_system.health_monitor.model_bundle = {
        "model": AlwaysAnomalousModel(),
        "features": [
            "sensor_criticality",
            "seq_delta",
            "message_age_ms",
            "reading",
            "reading_delta",
            "reading_zscore",
            "reading_std_last20",
            "identical_reading_streak",
            "mac_verified",
            "sensor_type",
            "reading_unit",
        ],
        "target": "sensor_health_label",
        "classes": ["anomalous_reading", "faulty", "normal"],
    }

    result = sensor_system.process_messages([make_message()])

    assert result["messages"][0]["status"] == "SENSOR_FAULT"
    assert result["messages"][0]["accepted"] is False
    assert list(
        sensor_system.feature_tracker.history["LIDAR_01"]
    ) == []
    assert "LIDAR_01" not in sensor_system.health_monitor.last_distance


def test_deadline_missed_reading_does_not_update_either_history():
    """A reading that misses its deadline must not enter either history."""

    result = sensor_system.process_messages([
        make_message(execution=10, overhead=2, deadline=5)
    ])

    assert result["messages"][0]["status"] == "DEADLINE_MISSED"
    assert result["messages"][0]["accepted"] is False
    assert list(
        sensor_system.feature_tracker.history["LIDAR_01"]
    ) == []
    assert "LIDAR_01" not in sensor_system.health_monitor.last_distance
