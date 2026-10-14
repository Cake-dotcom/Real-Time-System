
from src.security.message_monitor import MessageMonitor
from src.security.message_auth import create_mac
from src.security.sensor_health import SensorHealthMonitor
from src.scheduler.scheduler import schedule_message_tasks

SENSOR_KEYS = {
    "LIDAR_01": "demo_lidar_key",
    "RADAR_01": "demo_radar_key",
    "CAMERA_01": "demo_camera_key",
}

CRITICAL_SENSORS = {"LIDAR_01", "RADAR_01"}

message_monitor = MessageMonitor(SENSOR_KEYS)
health_monitor = SensorHealthMonitor(max_distance_change=20.0)


def process_messages(messages):
    verified_tasks = []
    message_results = []

    # Authenticate and check the health of every message first.
    for item in messages:
        message = item["message"]
        received_mac = item["mac"]

        authentication = message_monitor.verify(message, received_mac)

        if not authentication["valid"]:
            message_results.append({
                "sensor": message.get("sensor_id"),
                "status": "SECURITY_ALERT",
                "accepted": False,
                "reason": authentication["reason"],
            })
            continue

        health = health_monitor.check(message)

        if not health["healthy"]:
            message_results.append({
                "sensor": message.get("sensor_id"),
                "status": "SENSOR_FAULT",
                "accepted": False,
                "reason": health["issues"],
            })
            continue

        sensor_id = message["sensor_id"]

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

    # Accept data only if its task was scheduled and met its deadline.
    for result in message_results:
        sensor_id = result["sensor"]
        task_id = result.get("task_id")
        scheduled = scheduled_by_id.get(task_id)

        if result["status"] != "VERIFIED":
            continue

        if scheduled and scheduled["deadline_met"]:
            result["accepted"] = True
            result["status"] = "NORMAL"
            result["reason"] = "Authenticated, healthy, and processed before deadline"
        elif scheduled:
            result["status"] = "DEADLINE_MISSED"
            result["reason"] = "Message missed its deadline"
        elif task_id in schedule["deferred_sensors"]:
            result["status"] = "DEFERRED"
            result["reason"] = "Non-critical work deferred during fallback"
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

    print("Normal reading followed by sudden change:")
    pprint.pp(process_messages(test_messages))