
import math

from src.security.message_monitor import MessageMonitor
from src.security.message_auth import create_mac
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor
from src.scheduler.scheduler import schedule_message_tasks


SENSOR_KEYS = {
    "LIDAR_01": "demo_lidar_key",
    "RADAR_01": "demo_radar_key",
    "CAMERA_01": "demo_camera_key",
}

CRITICAL_SENSORS = {"LIDAR_01", "RADAR_01"}

SENSOR_METADATA = {
    "LIDAR_01": {
        "sensor_type": "lidar",
        "sensor_criticality": 3,
        "reading_unit": "m",
    },
    "RADAR_01": {
        "sensor_type": "radar",
        "sensor_criticality": 3,
        "reading_unit": "m",
    },
    "CAMERA_01": {
        "sensor_type": "camera",
        "sensor_criticality": 1,
        "reading_unit": "m",
    },
}

message_monitor = MessageMonitor(SENSOR_KEYS)
health_monitor = SensorHealthMonitor(max_distance_change=20.0)
feature_tracker = SensorFeatureTracker()


def process_messages(messages):
    verified_tasks = []
    message_results = []

    for item in messages:
        message = item["message"]
        received_mac = item["mac"]
        sensor_id = message.get("sensor_id")

        # 1. Authenticate and check sequence/replay protection first.
        authentication = message_monitor.verify(message, received_mac)

        if not authentication["valid"]:
            message_results.append({
                "sensor": sensor_id,
                "status": "SECURITY_ALERT",
                "accepted": False,
                "reason": authentication["reason"],
            })
            continue

        # 2. Validate the reading before updating feature history.
        distance = message.get("distance_m")

        if (
            not isinstance(distance, (int, float))
            or isinstance(distance, bool)
            or not math.isfinite(distance)
            or not 0.0 <= distance <= 200.0
        ):
            message_results.append({
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": ["Distance outside valid range"],
            })
            continue

        metadata = SENSOR_METADATA.get(sensor_id)

        if metadata is None:
            message_results.append({
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": ["Missing sensor metadata"],
            })
            continue

        # Supply an explicit age when available. The zero default is only
        # a simulator placeholder; it is not a measured message age.
        message_age_ms = item.get("message_age_ms", 0.0)

        if (
            not isinstance(message_age_ms, (int, float))
            or isinstance(message_age_ms, bool)
            or not math.isfinite(message_age_ms)
            or message_age_ms < 0
        ):
            message_results.append({
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": ["Invalid message age"],
            })
            continue

        # 3. Derive the feature columns used during model training.
        features = feature_tracker.build_features(
            message=message,
            sensor_type=metadata["sensor_type"],
            sensor_criticality=metadata["sensor_criticality"],
            reading_unit=metadata["reading_unit"],
            message_age_ms=message_age_ms,
            mac_verified=True,
        )

        # 4. Apply rule-based checks and ML sensor-health prediction.
        health = health_monitor.check(message, features=features)

        if not health["healthy"]:
            message_results.append({
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": health["issues"],
                "ml_prediction": health.get("prediction", "not_evaluated"),
                "risk_level": health.get("risk_level", "unknown"),
            })
            continue

        task_id = f"{sensor_id}-{message['sequence']}"

        verified_tasks.append({
            "task_id": task_id,
            "sensor": sensor_id,
            "critical": sensor_id in CRITICAL_SENSORS,
            "arrival_time": item["arrival_time"],
            "execution_time": item["execution_time"],
            "security_overhead": item["security_overhead"],
            "deadline": item["deadline"],
        })

        message_results.append({
            "sensor": sensor_id,
            "task_id": task_id,
            "status": "VERIFIED",
            "accepted": False,
            "reason": "Authenticated and healthy; awaiting scheduling",
            "ml_prediction": health.get("prediction", "not_evaluated"),
            "risk_level": health.get("risk_level", "unknown"),
        })

    if verified_tasks:
        schedule = schedule_message_tasks(verified_tasks)
    else:
        schedule = {
            "mode": "NO_VALID_TASKS",
            "results": [],
            "deferred_sensors": [],
        }

    scheduled_by_id = {
        result["task_id"]: result
        for result in schedule["results"]
    }

    # 5. Accept data only when its task was scheduled on time.
    for result in message_results:
        if result["status"] != "VERIFIED":
            continue

        task_id = result["task_id"]
        scheduled = scheduled_by_id.get(task_id)

        if scheduled and scheduled["deadline_met"]:
            result["accepted"] = True
            result["status"] = "NORMAL"
            result["reason"] = (
                "Authenticated, healthy, and processed before deadline"
            )

            # Update sensor history only after final acceptance.
            accepted_message = next(
                (
                    item["message"]
                    for item in messages
                    if (
                        item["message"].get("sensor_id") == result["sensor"]
                        and (
                            f"{item['message'].get('sensor_id')}-"
                            f"{item['message'].get('sequence')}"
                        ) == task_id
                    )
                ),
                None,
            )

            if accepted_message is not None:
                feature_tracker.commit_reading(accepted_message)
                health_monitor.commit_reading(accepted_message)
        elif scheduled:
            result["status"] = "DEADLINE_MISSED"
            result["reason"] = "Message missed its deadline"
        elif task_id in schedule["deferred_sensors"]:
            result["status"] = "DEFERRED"
            result["reason"] = (
                "Non-critical work deferred during fallback"
            )
        else:
            result["status"] = "NOT_SCHEDULED"
            result["reason"] = "No valid scheduling result"

    rejected_messages = [
        result for result in message_results
        if not result["accepted"]
    ]

    if schedule["mode"] == "NO_VALID_TASKS":
        safety_response = (
            "SAFETY_ALERT: No authenticated, healthy tasks available; "
            "request predefined safe-state response"
        )
    elif schedule["mode"] == "CRITICAL_DEADLINE_FAILURE":
        safety_response = (
            "SAFETY_ALERT: Critical deadlines infeasible; "
            "request predefined safe-state response"
        )
    elif schedule["mode"] == "CRITICAL_ONLY":
        safety_response = (
            "FALLBACK_ACTIVE: Critical sensors only; deferred "
            "non-critical messages must not be consumed as current data"
        )
    elif rejected_messages:
        safety_response = (
            "SECURITY_OR_SENSOR_WARNING: One or more messages rejected; "
            "continue only with eligible scheduled data"
        )
    else:
        safety_response = "Normal scheduling"

    return {
        "messages": message_results,
        "schedule": schedule,
        "safety_response": safety_response,
    }


if __name__ == "__main__":
    import pprint

    test_messages = [
        {
            "message": {
                "sensor_id": "LIDAR_01",
                "sequence": 1,
                "timestamp": 4001,
                "distance_m": 12.0,
            },
            "arrival_time": 0,
            "execution_time": 3,
            "security_overhead": 2,
            "deadline": 10,
        },
        {
            "message": {
                "sensor_id": "RADAR_01",
                "sequence": 1,
                "timestamp": 4001,
                "distance_m": 15.0,
            },
            "arrival_time": 0,
            "execution_time": 2,
            "security_overhead": 1,
            "deadline": 8,
        },
        {
            "message": {
                "sensor_id": "CAMERA_01",
                "sequence": 1,
                "timestamp": 4001,
                "distance_m": 18.0,
            },
            "arrival_time": 0,
            "execution_time": 4,
            "security_overhead": 2,
            "deadline": 7,
        },
        {
            "message": {
                "sensor_id": "CAMERA_01",
                "sequence": 2,
                "timestamp": 4002,
                "distance_m": 19.0,
            },
            "arrival_time": 1,
            "execution_time": 3,
            "security_overhead": 2,
            "deadline": 9,
        },
    ]

    for item in test_messages:
        item["mac"] = create_mac(
            item["message"],
            SENSOR_KEYS[item["message"]["sensor_id"]],
        )

    print("Sensor authentication, ML health, and scheduling test:")
    pprint.pp(process_messages(test_messages))
