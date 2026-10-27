import pytest

from src.security.risk_policy import select_validation_policy


def test_low_risk_uses_standard_validation():
    decision = select_validation_policy("low")

    assert decision.risk_level == "low"
    assert decision.validation_level == "standard"
    assert decision.simulated_extra_cost == 0.0


def test_sudden_change_escalates_low_risk_to_medium():
    decision = select_validation_policy("low", sudden_change=True)

    assert decision.risk_level == "medium"
    assert decision.validation_level == "additional"
    assert "temporal_consistency" in decision.required_checks


def test_medium_risk_requires_additional_checks():
    decision = select_validation_policy("medium")

    assert decision.validation_level == "additional"
    assert decision.simulated_extra_cost == 1.0
    assert "reading_plausibility" in decision.required_checks


def test_high_risk_requires_enhanced_checks():
    decision = select_validation_policy("high")

    assert decision.validation_level == "enhanced"
    assert decision.simulated_extra_cost == 2.0
    assert "stability_check" in decision.required_checks


def test_critical_risk_requires_rejection():
    decision = select_validation_policy("critical")

    assert decision.validation_level == "reject"


def test_unknown_risk_fails_safely():
    decision = select_validation_policy("unknown")

    assert decision.validation_level == "unavailable"


def test_missing_evidence_fails_safely():
    decision = select_validation_policy("low", missing_evidence=True)

    assert decision.risk_level == "unknown"
    assert decision.validation_level == "unavailable"


def test_unrecognized_risk_does_not_default_to_low():
    decision = select_validation_policy("unexpected")

    assert decision.risk_level == "unknown"
    assert decision.validation_level == "unavailable"

def test_confirmed_invalid_condition_is_rejected():
    decision = select_validation_policy(
        "high",
        confirmed_invalid=True,
    )

    assert decision.risk_level == "critical"
    assert decision.validation_level == "reject"
    assert decision.simulated_extra_cost == 0.0

def test_unknown_risk_has_no_permission_to_accept():
    decision = select_validation_policy(
        "unknown",
        missing_evidence=True,
    )

    assert decision.validation_level == "unavailable"
    assert decision.required_checks == ()
    assert decision.risk_level == "unknown"


def test_high_risk_never_skips_enhanced_checks():
    decision = select_validation_policy("high")

    assert decision.validation_level == "enhanced"
    assert {
        "temporal_consistency",
        "reading_plausibility",
        "stability_check",
    }.issubset(set(decision.required_checks))
