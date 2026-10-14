
from collections import defaultdict, deque
import math


class SensorFeatureTracker:
    """Derive model features and commit history only after acceptance."""

    def __init__(self, history_size=20):
        self.history_size = history_size
        self.history = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )
        self.last_sequence = {}

    def build_features(
        self,
        message,
        sensor_type,
        sensor_criticality,
        reading_unit,
        message_age_ms,
        mac_verified,
    ):
        """Calculate features without modifying history."""

        sensor_id = message["sensor_id"]
        reading = float(message["distance_m"])
        sequence = int(message["sequence"])

        if not math.isfinite(reading):
            raise ValueError("Reading must be finite")

        if not math.isfinite(float(message_age_ms)):
            raise ValueError("Message age must be finite")

        previous_readings = list(self.history[sensor_id])
        previous_sequence = self.last_sequence.get(sensor_id)

        if previous_readings:
            mean = sum(previous_readings) / len(previous_readings)

            variance = sum(
                (value - mean) ** 2
                for value in previous_readings
            ) / len(previous_readings)

            reading_std = math.sqrt(variance)
            reading_delta = reading - previous_readings[-1]

            reading_zscore = (
                (reading - mean) / reading_std
                if reading_std > 0
                else 0.0
            )

            identical_streak = 0
            for value in reversed(previous_readings):
                if value == reading:
                    identical_streak += 1
                else:
                    break
        else:
            reading_delta = 0.0
            reading_std = 0.0
            reading_zscore = 0.0
            identical_streak = 0

        seq_delta = (
            sequence - previous_sequence
            if previous_sequence is not None
            else 0
        )

        return {
            "sensor_criticality": sensor_criticality,
            "seq_delta": seq_delta,
            "message_age_ms": float(message_age_ms),
            "reading": reading,
            "reading_delta": reading_delta,
            "reading_zscore": reading_zscore,
            "reading_std_last20": reading_std,
            "identical_reading_streak": identical_streak,
            "mac_verified": int(bool(mac_verified)),
            "sensor_type": sensor_type,
            "reading_unit": reading_unit,
        }

    def commit_reading(self, message):
        """Add a reading to history only after it is accepted."""

        sensor_id = message["sensor_id"]
        reading = float(message["distance_m"])
        sequence = int(message["sequence"])

        self.history[sensor_id].append(reading)
        self.last_sequence[sensor_id] = sequence

    def reset(self, sensor_id=None):
        """Reset one sensor or all tracked sensors."""

        if sensor_id is None:
            self.history.clear()
            self.last_sequence.clear()
        else:
            self.history.pop(sensor_id, None)
            self.last_sequence.pop(sensor_id, None)
