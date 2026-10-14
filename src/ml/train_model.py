
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

DATASET_PATH = Path("data/raw/login_activity.csv")
MODEL_PATH = Path("models/login_risk_model.joblib")

FEATURES = [
    "failed_attempts_last_5min",
    "login_attempts_last_1min",
    "unique_accounts_targeted",
    "time_since_last_login_seconds",
    "unusual_login_time",
    "new_ip_for_user",
    "successful_login",
]

TARGET = "label"


def main():
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    df = pd.read_csv(DATASET_PATH)

    required = FEATURES + [TARGET]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    X = df[FEATURES]
    y = df[TARGET]

    # Keep the class proportions similar in both subsets.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("classifier", RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    print("\nClassification report:")
    print(classification_report(y_test, predictions, zero_division=0))

    print("Confusion matrix (labels in alphabetical order):")
    labels = sorted(y.unique())
    print("Label order:", labels)
    print(confusion_matrix(y_test, predictions, labels=labels))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "features": FEATURES, "labels": labels},
        MODEL_PATH,
    )

    print(f"\nTrained model saved to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
