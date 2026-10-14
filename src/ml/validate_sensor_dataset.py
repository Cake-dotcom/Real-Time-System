from pathlib import Path
import pandas as pd

DATASET = Path("data/raw/av_sensor_messages.csv")

REQUIRED_COLUMNS = [
    "message_id",
    "sensor_id",
    "sequence_number",
    "mac_verified",
    "deadline_missed",
    "task_outcome",
    "sensor_health_label",
    "scenario_label",
]


def main():
    if not DATASET.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET}")

    df = pd.read_csv(DATASET)

    print("=== Dataset Overview ===")
    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")
    print(f"Missing values: {df.isna().sum().sum()}")

    missing_columns = [
        column for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    print("\n=== Scenario Distribution ===")
    print(df["scenario_label"].value_counts(dropna=False).to_string())

    print("\n=== Sensor Health Distribution ===")
    print(df["sensor_health_label"].value_counts(dropna=False).to_string())

    print("\n=== Task Outcome Distribution ===")
    print(df["task_outcome"].value_counts(dropna=False).to_string())

    print("\n=== Basic Consistency Checks ===")

    print(
        f"Duplicate message IDs: "
        f"{df['message_id'].duplicated().sum()}"
    )

    invalid_mac = ~df["mac_verified"].isin([0, 1])
    print(f"Invalid MAC values: {invalid_mac.sum()}")

    invalid_deadline = ~df["deadline_missed"].isin([0, 1])
    print(f"Invalid deadline flags: {invalid_deadline.sum()}")

    expected_deadline = (
        df["task_outcome"] == "deadline_missed"
    ).astype(int)

    deadline_disagreements = (
        df["deadline_missed"] != expected_deadline
    ).sum()

    print(f"Deadline flag disagreements: {deadline_disagreements}")

    print("\n=== Missing Values by Column ===")
    print(df[REQUIRED_COLUMNS].isna().sum().to_string())

    print("\nValidation script completed.")


if __name__ == "__main__":
    main()