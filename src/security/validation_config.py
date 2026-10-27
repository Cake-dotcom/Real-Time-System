"""Project-defined parameters; none are official NIST sensor thresholds."""

MIN_READING = 0.0
MAX_READING = 200.0
MAX_READING_DELTA = 20.0
MAX_ABS_ZSCORE = 4.0
MAX_STD = 15.0
MAX_IDENTICAL_STREAK = 10
SIMULATED_EXTRA_COSTS = {"low": 0.0, "medium": 1.0, "high": 2.0}
IMPACT_BY_CRITICALITY = {1: "moderate", 2: "high", 3: "very_high"}
LIKELIHOOD_BY_PREDICTION = {
    "normal": "low", "anomalous_reading": "high", "faulty": "very_high",
}
