import pytest

from src.security.additional_validation import validate_additional_checks


NORMAL_FEATURES = {
    "reading": 12.0,
    "reading_delta": 0.5,
    "reading_zscore": 0.2,
    "reading_std_last20": 1.0,
    "identical_reading_streak": 0,
}


def test_normal_features_pass_all_enhanced_checks():
    result = validate_additional_checks(
        NORMAL_FEATURES,
        (
            "temporal_consistency",
            "reading_plausibility",
            "stability_check",
        ),
    )

    assert result["passed"] is True


def test_large_reading_change_fails_temporal_check():
    features = {**NORMAL_FEATURES, "reading_delta": 25.0}

    result = validate_additional_checks(
        features, ("temporal_consistency",)
    )

    assert result["passed"] is False


def test_extreme_zscore_fails_temporal_check():
    features = {**NORMAL_FEATURES, "reading_zscore": 5.0}

    result = validate_additional_checks(
        features, ("temporal_consistency",)
    )

    assert result["passed"] is False


def test_out_of_range_reading_fails_plausibility_check():
    features = {**NORMAL_FEATURES, "reading": 250.0}

    result = validate_additional_checks(
        features, ("reading_plausibility",)
    )

    assert result["passed"] is False


def test_long_identical_reading_streak_fails_stability_check():
    features = {**NORMAL_FEATURES, "identical_reading_streak": 10}

    result = validate_additional_checks(
        features, ("stability_check",)
    )

    assert result["passed"] is False


def test_missing_required_feature_fails_closed():
    features = dict(NORMAL_FEATURES)
    del features["reading_delta"]

    result = validate_additional_checks(
        features, ("temporal_consistency",)
    )

    assert result["passed"] is False


def test_unknown_check_fails_closed():
    result = validate_additional_checks(
        NORMAL_FEATURES, ("not_implemented",)
    )

    assert result["passed"] is False


def test_empty_check_list_does_not_report_success():
    result = validate_additional_checks(NORMAL_FEATURES, ())

    assert result["passed"] is False
