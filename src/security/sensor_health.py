
class SensorHealthMonitor:
    def __init__(self, max_distance_change=20.0):
        self.max_distance_change = max_distance_change
        self.last_distance = {}

    def check(self, message):
        issues = []
        sensor_id = message.get("sensor_id")
        distance = message.get("distance_m")

        if not isinstance(sensor_id, str) or not sensor_id:
            return {"healthy": False, "issues": ["Invalid sensor ID"]}

        if (
            not isinstance(distance, (int, float))
            or isinstance(distance, bool)
            or not 0.0 <= distance <= 200.0
        ):
            return {
                "healthy": False,
                "issues": ["Distance outside valid range"],
            }

        previous = self.last_distance.get(sensor_id)

        if previous is not None:
            change = abs(distance - previous)
            if change > self.max_distance_change:
                issues.append("Sudden distance change detected")

        # Update baseline only for readings that pass the checks.
        if not issues:
            self.last_distance[sensor_id] = distance

        return {"healthy": not issues, "issues": issues}


if __name__ == "__main__":
    monitor = SensorHealthMonitor(max_distance_change=20.0)

    readings = [12.5, 12.7, 80.0, 13.0]

    for sequence, distance in enumerate(readings, start=1):
        message = {
            "sensor_id": "LIDAR_01",
            "sequence": sequence,
            "distance_m": distance,
        }
        print(f"Reading {sequence}:", monitor.check(message))
