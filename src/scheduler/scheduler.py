
def schedule_message_tasks(tasks):
    """Try all sensors first, then fall back to critical sensors."""

    def run_edf(selected_tasks):
        pending = sorted(
            selected_tasks,
            key=lambda task: (task["arrival_time"], task["deadline"])
        )
        current_time = 0
        results = []

        while pending:
            ready = [
                task for task in pending
                if task["arrival_time"] <= current_time
            ]

            if not ready:
                current_time = pending[0]["arrival_time"]
                continue

            task = min(ready, key=lambda item: item["deadline"])
            pending.remove(task)

            start = current_time
            finish = start + task["execution_time"] + task["security_overhead"]

            results.append({
                "task_id": task["task_id"],
                "sensor": task["sensor"],
                "start": start,
                "finish": finish,
                "deadline": task["deadline"],
                "deadline_met": finish <= task["deadline"],
            })
            current_time = finish

        return results

    # First attempt: schedule every sensor.
    all_results = run_edf(tasks)

    if all(result["deadline_met"] for result in all_results):
        return {
            "mode": "ALL_SENSORS",
            "results": all_results,
            "deferred_sensors": [],
        }

    # Fallback: retain only critical sensors.
    critical_tasks = [task for task in tasks if task["critical"]]
    critical_results = run_edf(critical_tasks)
    critical_safe = all(
        result["deadline_met"] for result in critical_results
    )

    deferred = [
        task["task_id"] for task in tasks if not task["critical"]
    ]

    return {
        "mode": "CRITICAL_ONLY" if critical_safe else "CRITICAL_DEADLINE_FAILURE",
        "results": critical_results,
        "deferred_sensors": deferred,
    }


if __name__ == "__main__":
    tasks = [
        {
            "sensor": "LIDAR",
            "critical": True,
            "arrival_time": 0,
            "execution_time": 5,
            "security_overhead": 3,
            "deadline": 4,
        },
        {
            "sensor": "RADAR",
            "critical": True,
            "arrival_time": 0,
            "execution_time": 4,
            "security_overhead": 2,
            "deadline": 5,
        },
        {
            "sensor": "CAMERA",
            "critical": False,
            "arrival_time": 0,
            "execution_time": 3,
            "security_overhead": 2,
            "deadline": 10,
        },
    ]
    print(schedule_message_tasks(tasks))
