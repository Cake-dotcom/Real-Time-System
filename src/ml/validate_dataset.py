
from pathlib import Path

import pandas as pd

DATASET_PATH = Path("data/raw/login_activity.csv")

REQUIRED_COLUMNS = {
    "timestamp",
    "user_id",
    "source_ip",
    "failed_attempts_last_5min",
    "login_attempts_last_1min",
    "unique_accounts_targeted",
    "time_since_last_login_seconds",
    "unusual_login_time",
    "new_ip_for_user",
    "successful_login",
    "label",
}

VALID_LABELS = {"normal", "suspicious", "brute_force"}


def validate_dataset():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        print("Place your friend's CSV in data/raw/ and try again.")
        return

    df = pd.read_csv(DATASET_PATH)

    print(f"\nRows: {len(df)}")
    print(f"Columns: {len(df.columns)}")

    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        print("\nMissing required columns:")
        for column in sorted(missing_columns):
            print(f"  - {column}")
        return

    print("\nClass distribution:")
    print(df["label"].value_counts(dropna=False))

    print("\nMissing values:")
    print(df[list(REQUIRED_COLUMNS)].isnull().sum())

    print(f"\nDuplicate rows: {df.duplicated().sum()}")

    unknown_labels = set(df["label"].dropna().unique()) - VALID_LABELS
    if unknown_labels:
        print(f"\nUnexpected labels: {unknown_labels}")

    print("\nDataset preview:")
    print(df.head())

    if len(df) == 0:
        print("\nWARNING: Dataset is empty.")
    elif df["label"].isnull().any():
        print("\nWARNING: Some rows have missing labels.")
    elif unknown_labels:
        print("\nWARNING: Fix unexpected labels before training.")
    else:
        print("\nBasic validation complete.")
        print("Review the warnings and class distribution before training.")


if __name__ == "__main__":
    validate_dataset()
