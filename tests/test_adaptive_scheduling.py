from src.scheduler.scheduler import schedule_message_tasks


def test_additional_validation_cost_affects_deadline_feasibility():
    task = {
        "task_id": "LIDAR_01-1",
        "sensor": "LIDAR_01",
        "critical": True,
        "arrival_time": 0,
        "execution_time": 3,
        "security_overhead": 1 + 2,
        "deadline": 5,
    }

    result = schedule_message_tasks([task])

    assert result["results"][0]["finish"] == 6
    assert result["results"][0]["deadline_met"] is False
    assert result["mode"] == "CRITICAL_DEADLINE_FAILURE"
