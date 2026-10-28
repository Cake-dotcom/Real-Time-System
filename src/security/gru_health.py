"""GRU health evidence for authenticated SKAB-domain messages.

Cold start deliberately requires trusted commissioning context. Unavailable or
rejected incoming readings never build accepted history implicitly.
"""
from collections import deque
import math

from src.ml.gru_sensor_model import ARTIFACT, FEATURES, GRUPredictor
from src.security.validation_config import MIN_READING, MAX_READING, MAX_READING_DELTA


class GRUHealthMonitor:
    model_name = "GRU / SKAB"

    def __init__(self, model_path=ARTIFACT):
        self.predictor = None
        self.load_error = None
        self.history = {}
        self.scopes = {}
        self.last_distance = {}
        try:
            self.predictor = GRUPredictor(model_path)
        except Exception:
            self.load_error = "GRU artifact unavailable or invalid"

    def reset(self, sensor_id=None):
        for store in [self.history, self.scopes, self.last_distance]:
            if sensor_id is None:
                store.clear()
            else:
                store.pop(sensor_id, None)

    def bind_session(self, message):
        try:
            self.observation(message)
        except (ValueError, TypeError, KeyError):
            return False  # Malformed candidates must not destroy accepted context.
        source = message["sensor_id"]
        scope = (message.get("session_id"), message.get("recording_id"))
        if self.scopes.get(source) != scope:
            self.reset(source)
            self.scopes[source] = scope
            return True
        return False

    @staticmethod
    def observation(message):
        if message.get("sensor_domain") != "SKAB" or not isinstance(message.get("recording_id"), str) or not message["recording_id"]:
            raise ValueError("SKAB domain and recording identifier required; vehicle distance is not a SKAB feature")
        values = message.get("sensor_values")
        if not isinstance(values, dict) or set(values) != set(FEATURES):
            raise ValueError("Eight named SKAB measurements required")
        ordered = [values[k] for k in FEATURES]
        timestamp = message.get("timestamp")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in ordered + [timestamp]):
            raise ValueError("Nonfinite or malformed SKAB measurement/timestamp")
        return float(timestamp), ordered

    def commission_trusted_history(self, source, session_id, recording_id, observations):
        """Administrative API ONLY: externally trusted chronological context, not message ingestion.

        Caller must establish provenance and bind to the receiver's current session.
        This does not mark messages accepted, advance replay state, or authorize data.
        """
        if self.predictor is None:
            raise ValueError("Model unavailable")
        rows = list(observations)
        if len(rows) != self.predictor.length - 1:
            raise ValueError("Commissioning context must be exactly T-1 observations")
        validated = []
        for row in rows:
            if row.get("recording_id") != recording_id or row.get("sensor_id") != source:
                raise ValueError("Commissioning source/run mismatch")
            validated.append(self.observation(row))
        if any(not 0 < b[0] - a[0] <= 2 for a, b in zip(validated, validated[1:])):
            raise ValueError("Commissioning chronology/gap invalid")
        if not session_id:
            raise ValueError("Session binding required")
        self.reset(source)
        self.scopes[source] = (session_id, recording_id)
        self.history[source] = deque(validated, maxlen=self.predictor.length - 1)

    def check(self, message, features=None):
        result = {"healthy": False, "prediction": "not_evaluated", "risk_level": "unknown",
                  "issues": [], "model": self.model_name, "anomaly_score": None,
                  "inference_ms": None, "sequence_ready": False,
                  "window_length": self.predictor.length if self.predictor else None}
        try:
            if self.predictor is None:
                raise ValueError(self.load_error)
            source = message["sensor_id"]
            scope = (message.get("session_id"), message.get("recording_id"))
            if self.scopes.get(source) != scope:
                raise ValueError("Session/run context unavailable")
            current = self.observation(message)
            distance = message.get("distance_m")
            if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or not MIN_READING <= distance <= MAX_READING:
                raise ValueError("Invalid simulator distance input")
            history = list(self.history.get(source, ()))
            result["history_length"] = len(history)
            if len(history) != self.predictor.length - 1:
                raise ValueError("Insufficient accepted/commissioned history; trusted commissioning required")
            rows = history + [current]
            if any(not 0 < b[0] - a[0] <= 2 for a, b in zip(rows, rows[1:])):
                raise ValueError("Nonchronological or stale history; recommission required")
            output = self.predictor.predict([row[1] for row in rows])
            if output["prediction"] not in {"normal", "anomalous"} or not math.isfinite(output["anomaly_score"]) or not 0 <= output["anomaly_score"] <= 1:
                raise ValueError("Unknown or invalid GRU prediction")
            result.update(output, sequence_ready=True)
            result["dataset_prediction"] = output["prediction"]
            # Explicit statistical anomaly -> existing policy's anomalous-reading category.
            result["prediction"] = "anomalous_reading" if output["prediction"] == "anomalous" else "normal"
            result["risk_level"] = "high" if result["prediction"] == "anomalous_reading" else "low"
            if result["prediction"] != "normal":
                result["issues"].append("GRU classified process measurements as anomalous; not an attribution of malice")
            if source in self.last_distance and abs(distance - self.last_distance[source]) > MAX_READING_DELTA:
                result["issues"].append("Sudden distance change detected")
            result["healthy"] = not result["issues"]
        except Exception:
            result.update(healthy=False, prediction="not_evaluated", risk_level="unknown",
                          anomaly_score=None, probabilities=None,
                          issues=["GRU evidence unavailable: invalid domain/input, artifact, session, or temporal context"])
        return result

    def commit_reading(self, message):
        """Called only after authentication, health, policy and deadline acceptance."""
        source = message["sensor_id"]
        self.history[source].append(self.observation(message))
        self.last_distance[source] = message["distance_m"]
