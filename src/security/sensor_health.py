
from pathlib import Path

import joblib
import pandas as pd
from src.security.validation_config import MIN_READING, MAX_READING, MAX_READING_DELTA


MODEL_PATH = Path("models/sensor_health_model.joblib")


class SensorHealthMonitor:
    # Retained vehicle-domain RF baseline. The live system defaults to GRUHealthMonitor.
    model_name = "Random Forest / vehicle baseline"
    def __init__(self, max_distance_change=MAX_READING_DELTA, model_path=MODEL_PATH):
        self.max_distance_change = max_distance_change
        self.last_distance = {}
        self.model_bundle = None

        if model_path.exists():
            self.model_bundle = joblib.load(model_path)

    def check(self, message, features=None):
        """Check a message without modifying accepted-reading history."""
        issues = []
        sensor_id = message.get("sensor_id")
        distance = message.get("distance_m")

        if not isinstance(sensor_id, str) or not sensor_id:
            return {
                "healthy": False,
                "issues": ["Invalid sensor ID"],
                "prediction": "faulty",
                "risk_level": "critical",
            }

        if (
            not isinstance(distance, (int, float))
            or isinstance(distance, bool)
            or not MIN_READING <= distance <= MAX_READING
        ):
            return {
                "healthy": False,
                "issues": ["Distance outside valid range"],
                "prediction": "faulty",
                "risk_level": "critical",
            }

        previous = self.last_distance.get(sensor_id)

        if (
            previous is not None
            and abs(distance - previous) > self.max_distance_change
        ):
            issues.append("Sudden distance change detected")

        prediction = "not_evaluated"
        risk_level = "low"

        if self.model_bundle is None or features is None:
            return {"healthy": False, "issues": [*issues, "ML evidence unavailable"],
                    "prediction": prediction, "risk_level": "unknown"}

        if self.model_bundle is not None and features is not None:
            required = self.model_bundle["features"]
            missing = [name for name in required if name not in features]

            if missing:
                return {
                    "healthy": False,
                    "issues": [
                        "Missing ML features: " + ", ".join(missing)
                    ],
                    "prediction": "not_evaluated",
                    "risk_level": "unknown",
                }

            model_input = pd.DataFrame(
                [{name: features[name] for name in required}]
            )

            prediction = self.model_bundle["model"].predict(
                model_input
            )[0]

            if prediction == "faulty":
                risk_level = "critical"
                issues.append("ML model classified sensor as faulty")
            elif prediction == "anomalous_reading":
                risk_level = "high"
                issues.append(
                    "ML model classified reading as anomalous"
                )

        return {
            "healthy": not issues,
            "issues": issues,
            "prediction": prediction,
            "risk_level": risk_level,
        }

    def commit_reading(self, message):
        """Record a reading only after final pipeline acceptance."""
        sensor_id = message["sensor_id"]
        distance = message["distance_m"]

        self.last_distance[sensor_id] = distance

    def reset(self, sensor_id=None):
        """Reset one sensor or all sensor-health history."""
        if sensor_id is None:
            self.last_distance.clear()
        else:
            self.last_distance.pop(sensor_id, None)


if __name__ == "__main__":
    monitor = SensorHealthMonitor()

    readings = [12.5, 12.7, 80.0, 13.0]

    for sequence, distance in enumerate(readings, start=1):
        message = {
            "sensor_id": "LIDAR_01",
            "sequence": sequence,
            "distance_m": distance,
        }
        result = monitor.check(message)
        print(f"Reading {sequence}:", result)

        # This standalone demonstration assumes healthy readings
        # are accepted; the actual pipeline commits after scheduling.
        if result["healthy"]:
            monitor.commit_reading(message)
