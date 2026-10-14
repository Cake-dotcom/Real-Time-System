
from pathlib import Path

import joblib
import pandas as pd

MODEL_PATH = Path("models/login_risk_model.joblib")

# Initial demonstration thresholds; we will calibrate them later.
RISK_THRESHOLDS = {
    "low": 30,
    "medium": 60,
    "high": 85,
}


class RiskEngine:
    def __init__(self):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

        saved = joblib.load(MODEL_PATH)
        self.model = saved["model"]
        self.features = saved["features"]

    def assess(self, event):
        # Require every feature used during training.
        missing = set(self.features) - set(event)
        if missing:
            raise ValueError(f"Missing features: {sorted(missing)}")

        row = pd.DataFrame(
            [{feature: event[feature] for feature in self.features}]
        )

        probabilities = self.model.predict_proba(row)[0]
        classes = self.model.named_steps["classifier"].classes_

        scores = dict(zip(classes, probabilities))
        prediction = max(scores, key=scores.get)

        # Initial risk mapping for demonstration.
        # These are policy scores, not calibrated attack probabilities.
        risk = (
            100 * scores.get("brute_force", 0)
            + 70 * scores.get("suspicious", 0)
            + 5 * scores.get("normal", 0)
        )

        risk = round(float(risk), 2)

        if risk < RISK_THRESHOLDS["low"]:
            level = "low"
        elif risk < RISK_THRESHOLDS["medium"]:
            level = "medium"
        elif risk < RISK_THRESHOLDS["high"]:
            level = "high"
        else:
            level = "critical"

        return {
            "prediction": prediction,
            "class_probabilities": {
                label: round(float(probability), 4)
                for label, probability in scores.items()
            },
            "risk_score": risk,
            "risk_level": level,
        }


if __name__ == "__main__":
    engine = RiskEngine()

    example_event = {
        "failed_attempts_last_5min": 35,
        "login_attempts_last_1min": 25,
        "unique_accounts_targeted": 2,
        "time_since_last_login_seconds": 20,
        "unusual_login_time": 1,
        "new_ip_for_user": 1,
        "successful_login": 0,
    }

    print(engine.assess(example_event))
