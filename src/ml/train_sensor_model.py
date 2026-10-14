from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    balanced_accuracy_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier

DATASET = Path("data/raw/av_sensor_messages.csv")
MODEL_PATH = Path("models/sensor_health_model.joblib")
REPORT_PATH = Path("results/sensor_model_report.txt")

TARGET = "sensor_health_label"

# Use sensor/readings and message-integrity context.
# Exclude identifiers, target-derived labels, and post-scheduling outcomes.
NUMERIC_FEATURES = [
    "sensor_criticality",
    "seq_delta",
    "message_age_ms",
    "reading",
    "reading_delta",
    "reading_zscore",
    "reading_std_last20",
    "identical_reading_streak",
    "mac_verified",
]

CATEGORICAL_FEATURES = [
    "sensor_type",
    "reading_unit",
]

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def main():
    df = pd.read_csv(DATASET)

    required = FEATURES + [TARGET, "run_id"]
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"Missing dataset columns: {missing}")

    df = df.dropna(subset=[TARGET, "run_id"]).copy()

    X = df[FEATURES]
    y = df[TARGET]
    groups = df["run_id"]

    # Keep entire runs in either train or test to reduce run-level leakage.
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.25,
        random_state=42,
    )
    train_idx, test_idx = next(splitter.split(X, y, groups=groups))

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    preprocessing = ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
    ])

    model = Pipeline([
        ("preprocessing", preprocessing),
        (
            "classifier",
            RandomForestClassifier(
                n_estimators=300,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    accuracy = accuracy_score(y_test, predictions)
    balanced_accuracy = balanced_accuracy_score(y_test, predictions)
    report = classification_report(
        y_test,
        predictions,
        labels=["normal", "anomalous_reading", "faulty"],
        zero_division=0,
    )
    matrix = confusion_matrix(
        y_test,
        predictions,
        labels=["normal", "anomalous_reading", "faulty"],
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "target": TARGET,
            "classes": list(model.classes_),
        },
        MODEL_PATH,
    )

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        file.write(f"Dataset records: {len(df)}\n")
        file.write(f"Training records: {len(train_idx)}\n")
        file.write(f"Test records: {len(test_idx)}\n")
        file.write(f"Training runs: {groups.iloc[train_idx].nunique()}\n")
        file.write(f"Test runs: {groups.iloc[test_idx].nunique()}\n")
        file.write(f"Accuracy: {accuracy:.4f}\n")
        file.write(f"Balanced accuracy: {balanced_accuracy:.4f}\n\n")
        file.write("Classification report:\n")
        file.write(report)
        file.write("\nConfusion matrix\n")
        file.write("Class order: normal, anomalous_reading, faulty\n")
        file.write(str(matrix))
        file.write("\n")

    print(f"Dataset records: {len(df)}")
    print(f"Training records: {len(train_idx)}")
    print(f"Test records: {len(test_idx)}")
    print(f"Training runs: {groups.iloc[train_idx].nunique()}")
    print(f"Test runs: {groups.iloc[test_idx].nunique()}")
    print(f"\nAccuracy: {accuracy:.4f}")
    print(f"Balanced accuracy: {balanced_accuracy:.4f}")
    print("\nClassification report:")
    print(report)
    print("Confusion matrix (normal, anomalous_reading, faulty):")
    print(matrix)
    print(f"\nModel saved to: {MODEL_PATH}")
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()