
import math
from dataclasses import asdict

from src.security.message_monitor import MessageMonitor
from src.security.source_sessions import authenticate_sender
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor
from src.scheduler.scheduler import schedule_message_tasks
from src.security.risk_policy import assess_sensor_risk
from src.security.additional_validation import validate_additional_checks
from src.security.validation_config import MIN_READING, MAX_READING, MAX_READING_DELTA


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
health_monitor = SensorHealthMonitor(max_distance_change=MAX_READING_DELTA)
feature_tracker = SensorFeatureTracker()


def process_messages(messages):
    verified_tasks = []
    message_results = []
    accepted_candidates = {}

    for item in messages:
        item = item if isinstance(item, dict) else {}
        message = item.get("message")
        received_mac = item.get("mac")
        sensor_id = message.get("sensor_id") if isinstance(message, dict) else None

        # 1. Authenticate and check sequence/replay protection first.
        authentication = message_monitor.verify(message, received_mac)
        audit = {"authentication": authentication["authentication"],
                 "source_authentication": authentication["source_authentication"],
                 "session_reused": authentication["session_reused"],
                 "measured_verification_ns": authentication["measured_verification_ns"],
                 "simulated_handshake_cost": authentication["simulated_handshake_cost"],
                 "replay": authentication["replay"], "policy": None,
                 "additional_checks": None, "simulated_extra_cost": 0.0,
                 "deadline_met": None}

        if not authentication["valid"]:
            message_results.append({
                **audit,
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
            or not MIN_READING <= distance <= MAX_READING
        ):
            message_results.append({
                **audit,
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": ["Distance outside valid range"],
            })
            continue

        metadata = SENSOR_METADATA.get(sensor_id)

        if metadata is None:
            message_results.append({
                **audit,
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
                **audit,
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": ["Invalid message age"],
            })
            continue

        # Scheduling fields are trusted simulator inputs, but must be finite
        # and non-negative to avoid nonsensical deadline acceptance.
        timing_fields = ("arrival_time", "execution_time", "security_overhead", "deadline")
        if any(not isinstance(item.get(name), (int, float))
               or isinstance(item.get(name), bool)
               or not math.isfinite(item[name]) or item[name] < 0
               for name in timing_fields):
            message_results.append({**audit, "sensor": sensor_id,
                                    "status": "INVALID_INPUT", "accepted": False,
                                    "reason": "Invalid scheduling parameters"})
            continue

        # 3. Derive features from previously accepted history.
        features = feature_tracker.build_features(
            message=message,
            sensor_type=metadata["sensor_type"],
            sensor_criticality=metadata["sensor_criticality"],
            reading_unit=metadata["reading_unit"],
            message_age_ms=message_age_ms,
            mac_verified=True,
        )

        # 4. Apply rule-based checks and ML sensor-health prediction.
        try:
            health = health_monitor.check(message, features=features)
        except (KeyError, TypeError, ValueError, RuntimeError):
            health = {"healthy": False, "prediction": "not_evaluated",
                      "risk_level": "unknown", "issues": ["Health evaluation unavailable"]}

        # 5. Assess evidence, then execute every selected check. Mandatory
        # failures have already continued above and can never reach this code.
        decision = assess_sensor_risk(health, features)
        checks = (validate_additional_checks(features, decision.required_checks)
                  if decision.required_checks else None)
        audit.update({"health": health, "policy": asdict(decision),
                      "additional_checks": checks,
                      "simulated_extra_cost": decision.simulated_extra_cost})
        if decision.validation_level == "unavailable":
            message_results.append({**audit, "sensor": sensor_id,
                                    "status": "POLICY_UNAVAILABLE", "accepted": False,
                                    "reason": decision.reason})
            continue

        if not health["healthy"]:
            message_results.append({
                **audit,
                "sensor": sensor_id,
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": health["issues"],
                "ml_prediction": health.get("prediction", "not_evaluated"),
                "risk_level": health.get("risk_level", "unknown"),
            })
            continue

        if (decision.response != "validate" or checks is None or not checks["passed"]):
            message_results.append({**audit, "sensor": sensor_id,
                                    "status": "POLICY_REJECTED", "accepted": False,
                                    "reason": "Policy rejected or required validation failed"})
            continue

        task_id = f"{sensor_id}-{message['sequence']}"
        accepted_candidates[task_id] = message

        verified_tasks.append({
            "task_id": task_id,
            "sensor": sensor_id,
            "critical": sensor_id in CRITICAL_SENSORS,
            "arrival_time": item["arrival_time"],
            "execution_time": item["execution_time"],
            "security_overhead": (item["security_overhead"] + decision.simulated_extra_cost
                                  + authentication["simulated_handshake_cost"]),
            "deadline": item["deadline"],
        })

        message_results.append({
            **audit,
            "baseline_security_overhead": item["security_overhead"],
            "total_security_overhead": (item["security_overhead"] + decision.simulated_extra_cost
                                        + authentication["simulated_handshake_cost"]),
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

    # Accept data only when its task was scheduled on time.
    for result in message_results:
        if result["status"] != "VERIFIED":
            continue

        task_id = result["task_id"]
        scheduled = scheduled_by_id.get(task_id)
        result["deadline_met"] = scheduled["deadline_met"] if scheduled else None

        if scheduled and scheduled["deadline_met"]:
            result["accepted"] = True
            result["status"] = "NORMAL"
            result["reason"] = (
                "Authenticated, healthy, and processed before deadline"
            )

            # Update sensor history only after final acceptance.
            accepted_message = accepted_candidates[task_id]

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
        "authentication_metrics": dict(message_monitor.sessions.metrics),
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

    senders = {}
    for item in test_messages:
        source = item["message"]["sensor_id"]
        if source not in senders:
            senders[source] = authenticate_sender(message_monitor.sessions, source, SENSOR_KEYS[source])
        item["message"], item["mac"] = senders[source].sign(item["message"])

    print("Sensor authentication, ML health, and scheduling test:")
    pprint.pp(process_messages(test_messages))
