"""Additional sensor validation checks.

These checks supplement mandatory authentication and replay protection.
They do not replace either mandatory security check.
"""

import math
from src.security.validation_config import (
    MIN_READING, MAX_READING, MAX_READING_DELTA, MAX_ABS_ZSCORE,
    MAX_STD, MAX_IDENTICAL_STREAK,
)


def validate_additional_checks(features, required_checks):
    """Run the requested checks and return auditable results."""

    results = {}

    for check in required_checks:
        if check == "mandatory_sensor_checks":
            # Authentication, replay, and basic range validation must
            # already have been performed by the main pipeline.
            results[check] = {
                "passed": False,
                "reason": "Cannot attest mandatory gates from sensor features.",
            }

        elif check == "temporal_consistency":
            delta = features.get("reading_delta")
            zscore = features.get("reading_zscore")

            valid = (
                isinstance(delta, (int, float))
                and not isinstance(delta, bool)
                and math.isfinite(delta)
                and isinstance(zscore, (int, float))
                and not isinstance(zscore, bool)
                and math.isfinite(zscore)
                and abs(delta) <= MAX_READING_DELTA
                and abs(zscore) <= MAX_ABS_ZSCORE
            )

            results[check] = {
                "passed": valid,
                "reason": (
                    "Temporal features are within configured limits."
                    if valid
                    else "Temporal inconsistency or unavailable features."
                ),
            }

        elif check == "reading_plausibility":
            reading = features.get("reading")

            valid = (
                isinstance(reading, (int, float))
                and not isinstance(reading, bool)
                and math.isfinite(reading)
                and MIN_READING <= reading <= MAX_READING
            )

            results[check] = {
                "passed": valid,
                "reason": (
                    "Reading is within the configured physical range."
                    if valid
                    else "Reading is invalid or outside the configured range."
                ),
            }

        elif check == "stability_check":
            std = features.get("reading_std_last20")
            streak = features.get("identical_reading_streak")

            valid = (
                isinstance(std, (int, float))
                and not isinstance(std, bool)
                and math.isfinite(std)
                and 0 <= std <= MAX_STD
                and isinstance(streak, int)
                and not isinstance(streak, bool)
                and 0 <= streak < MAX_IDENTICAL_STREAK
            )

            results[check] = {
                "passed": valid,
                "reason": (
                    "Stability features are within configured limits."
                    if valid
                    else "Unstable or potentially stuck sensor reading."
                ),
            }

        else:
            # Unknown checks must not silently pass.
            results[check] = {
                "passed": False,
                "reason": "Unimplemented validation check.",
            }

    return {
        "passed": bool(results) and all(
            item["passed"] for item in results.values()
        ),
        "checks": results,
    }
