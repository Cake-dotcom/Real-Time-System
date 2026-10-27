"""Risk-adaptive additional-validation policy.

Risk thresholds and validation costs are provisional simulation parameters.
They are not measured execution times.
"""

from dataclasses import dataclass, replace
import math

from src.security.validation_config import (
    IMPACT_BY_CRITICALITY, LIKELIHOOD_BY_PREDICTION, SIMULATED_EXTRA_COSTS,
)

FRAMEWORK = "NIST SP 800-30 Rev. 1 / project sensor profile v1"
SOURCE_SECTION = "Section 3.2 Task 2-6; Appendix I Table I-2 (p. I-1)"
SOURCE_URL = "https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-30r1.pdf"
LEVELS = ("very_low", "low", "moderate", "high", "very_high")
# Exact qualitative cells from Table I-2; rows likelihood, columns impact.
RISK_MATRIX = {
    "very_low": ("very_low", "very_low", "very_low", "low", "low"),
    "low": ("very_low", "low", "low", "low", "moderate"),
    "moderate": ("very_low", "low", "moderate", "moderate", "high"),
    "high": ("very_low", "low", "moderate", "high", "very_high"),
    "very_high": ("very_low", "low", "moderate", "high", "very_high"),
}


@dataclass(frozen=True)
class ValidationDecision:
    risk_level: str
    validation_level: str
    required_checks: tuple[str, ...]
    simulated_extra_cost: float
    reason: str
    framework: str = FRAMEWORK
    source_section: str = SOURCE_SECTION
    source_url: str = SOURCE_URL
    likelihood: str = "unknown"
    impact: str = "unknown"
    matrix_risk: str = "unknown"
    response: str = "validate"
    evidence: tuple[str, ...] = ()
    uncertainty: str = "Project-defined qualitative proxies; not calibrated probabilities."


# Provisional simulation parameters, in the scheduler's time units.
# These values must be documented as assumptions, not measured costs.
# Costs are imported from the central project configuration.


def assess_sensor_risk(health, features):
    """Assess authenticated sensor evidence using NIST's exemplary matrix.

    This function cannot authenticate or accept a message. The caller enforces
    mandatory gates, health rejection, check outcomes and deadline feasibility.
    """
    prediction = health.get("prediction")
    criticality = features.get("sensor_criticality")
    required = ("reading", "reading_delta", "reading_zscore",
                "reading_std_last20", "identical_reading_streak",
                "message_age_ms", "seq_delta")
    missing = [name for name in required if (
        not isinstance(features.get(name), (int, float))
        or isinstance(features.get(name), bool)
        or not math.isfinite(features[name])
    )]
    if (prediction not in LIKELIHOOD_BY_PREDICTION
            or not isinstance(criticality, int) or isinstance(criticality, bool)
            or criticality not in IMPACT_BY_CRITICALITY
            or features.get("mac_verified") != 1
            or health.get("risk_level") == "unknown"
            or not isinstance(health.get("healthy"), bool)
            or missing):
        return replace(
            select_validation_policy("unknown"), response="defer",
            evidence=(f"prediction={prediction}", f"criticality={criticality}",
                      f"missing_or_invalid_features={missing}"),
            uncertainty="Required evidence missing, invalid, or unrecognized.",
        )
    likelihood = LIKELIHOOD_BY_PREDICTION[prediction]
    if health.get("issues") and prediction == "normal":
        likelihood = "moderate"
    impact = IMPACT_BY_CRITICALITY[criticality]
    matrix_risk = RISK_MATRIX[likelihood][LEVELS.index(impact)]
    local_level = {"very_low": "low", "low": "low", "moderate": "medium",
                   "high": "high", "very_high": "critical"}[matrix_risk]
    decision = select_validation_policy(local_level)
    response = "validate" if health["healthy"] else "reject"
    if decision.validation_level == "reject":
        response = "reject"
    return replace(
        decision, likelihood=likelihood, impact=impact, matrix_risk=matrix_risk,
        response=response,
        evidence=(f"health_prediction={prediction}", f"sensor_criticality={criticality}",
                  *tuple(health.get("issues", ()))),
        reason=(f"Table I-2: {likelihood} likelihood and {impact} impact yield "
                f"{matrix_risk} risk. {decision.reason} "
                + ("Unhealthy readings remain rejected." if not health["healthy"] else "")),
    )


def select_validation_policy(
    risk_level,
    sudden_change=False,
    missing_evidence=False,
    confirmed_invalid=False,
):
    """Project response selector; compatibility API for already assessed risk.

    The live pipeline calls assess_sensor_risk, not this helper directly.
    """

    if confirmed_invalid:
        return ValidationDecision(
            risk_level="critical",
            validation_level="reject",
            response="reject",
            required_checks=(),
            simulated_extra_cost=0.0,
            reason="A confirmed invalid condition requires rejection.",
        )

    if missing_evidence or risk_level == "unknown":
        return ValidationDecision(
            risk_level="unknown",
            validation_level="unavailable",
            response="defer",
            required_checks=(),
            simulated_extra_cost=0.0,
            reason="Risk evidence is unavailable; fail safely.",
        )

    if risk_level == "critical":
        return ValidationDecision(
            risk_level="critical",
            validation_level="reject",
            response="reject",
            required_checks=(),
            simulated_extra_cost=0.0,
            reason="Critical risk requires rejection under the current policy.",
        )

    if risk_level == "high":
        return ValidationDecision(
            risk_level="high",
            validation_level="enhanced",
            required_checks=(
                "temporal_consistency",
                "reading_plausibility",
                "stability_check",
            ),
            simulated_extra_cost=SIMULATED_EXTRA_COSTS["high"],
            reason="High risk requires enhanced validation.",
        )

    if risk_level == "medium" or sudden_change:
        return ValidationDecision(
            risk_level="medium",
            validation_level="additional",
            required_checks=(
                "temporal_consistency",
                "reading_plausibility",
            ),
            simulated_extra_cost=SIMULATED_EXTRA_COSTS["medium"],
            reason="Medium risk requires additional consistency checks.",
        )

    if risk_level == "low":
        return ValidationDecision(
            risk_level="low",
            validation_level="standard",
            required_checks=("reading_plausibility",),
            simulated_extra_cost=SIMULATED_EXTRA_COSTS["low"],
            reason="No elevated risk evidence was supplied.",
        )

    return ValidationDecision(
        risk_level="unknown",
        validation_level="unavailable",
        response="defer",
        required_checks=(),
        simulated_extra_cost=0.0,
        reason="Unrecognized risk level; fail safely.",
    )
