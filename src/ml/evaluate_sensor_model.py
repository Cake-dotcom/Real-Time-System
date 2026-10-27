"""Reproduce grouped evaluation without overwriting trained model artifacts."""
import hashlib
import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit, LeaveOneGroupOut

from src.ml.train_sensor_model import DATASET, MODEL_PATH, FEATURES, TARGET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-runs", action="store_true", help="Also refit four leave-one-run-out folds")
    parser.add_argument("--output-dir", type=Path, default=Path("results/policy_evaluation"))
    args = parser.parse_args()
    df = pd.read_csv(DATASET).dropna(subset=[TARGET, "run_id"])
    saved = joblib.load(MODEL_PATH)
    if saved["features"] != FEATURES:
        raise ValueError("Saved model feature schema differs from training script")
    train, test = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
                       .split(df[FEATURES], df[TARGET], groups=df.run_id))
    train_runs = sorted(df.iloc[train].run_id.unique().tolist())
    test_runs = sorted(df.iloc[test].run_id.unique().tolist())
    assert not set(train_runs) & set(test_runs)
    # Clone and refit in memory: the saved artifact lacks split provenance.
    model = clone(saved["model"])
    model.fit(df.iloc[train][FEATURES], df.iloc[train][TARGET])
    labels = ["normal", "anomalous_reading", "faulty"]
    expected = df.iloc[test][TARGET]
    predicted = model.predict(df.iloc[test][FEATURES])
    report = {
        "method": "In-memory refit of saved pipeline configuration; GroupShuffleSplit seed 42",
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "records": len(df), "columns": len(df.columns), "features": FEATURES,
        "training_runs": train_runs, "test_runs": test_runs,
        "training_records": len(train), "test_records": len(test),
        "accuracy": accuracy_score(expected, predicted),
        "balanced_accuracy": balanced_accuracy_score(expected, predicted),
        "classification_report": classification_report(expected, predicted, labels=labels,
                                                         output_dict=True, zero_division=0),
        "confusion_matrix_class_order": labels,
        "confusion_matrix": confusion_matrix(expected, predicted, labels=labels).tolist(),
        "limitations": "Four runs, one holdout; feature-generation provenance is not established."
    }
    saved_predictions = saved["model"].predict(df.iloc[test][FEATURES])
    report["saved_artifact_diagnostic"] = {
        "warning": "Split provenance is absent from the saved bundle; this is a diagnostic, not independent generalization evidence.",
        "accuracy_on_reconstructed_holdout": accuracy_score(expected, saved_predictions),
        "agreement_with_fresh_refit": float((saved_predictions == predicted).mean()),
        "classification_report": classification_report(expected, saved_predictions, labels=labels,
                                                         output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(expected, saved_predictions, labels=labels).tolist(),
    }
    if args.all_runs:
        folds = []
        for fit_indices, holdout_indices in LeaveOneGroupOut().split(df[FEATURES], df[TARGET], df.run_id):
            fold_model = clone(saved["model"])
            fold_model.fit(df.iloc[fit_indices][FEATURES], df.iloc[fit_indices][TARGET])
            truth = df.iloc[holdout_indices][TARGET]
            guesses = fold_model.predict(df.iloc[holdout_indices][FEATURES])
            folds.append({"test_run": int(df.iloc[holdout_indices].run_id.iloc[0]),
                          "training_runs": sorted(df.iloc[fit_indices].run_id.unique().tolist()),
                          "accuracy": accuracy_score(truth, guesses),
                          "balanced_accuracy": balanced_accuracy_score(truth, guesses),
                          "classification_report": classification_report(truth, guesses, labels=labels,
                                                                          output_dict=True, zero_division=0),
                          "confusion_matrix": confusion_matrix(truth, guesses, labels=labels).tolist()})
        report["leave_one_run_out"] = folds
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "sensor_model_evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
