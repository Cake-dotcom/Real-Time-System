from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DATASET = Path("data/raw/av_sensor_messages.csv")
OUTPUT_DIR = Path("results")


def main():
    df = pd.read_csv(DATASET)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Dataset Overview ===")
    print(f"Total records: {len(df)}")
    print(f"Unique runs: {df['run_id'].nunique()}")
    print(f"Unique sensors: {df['sensor_id'].nunique()}")

    print("\n=== Scenario Distribution ===")
    print(df["scenario_label"].value_counts().to_string())

    print("\n=== Authentication Results ===")
    print(df["mac_verified"].value_counts().rename({
        0: "MAC rejected",
        1: "MAC verified",
    }).to_string())

    print("\n=== Sensor Health ===")
    print(df["sensor_health_label"].value_counts().to_string())

    print("\n=== Task Outcomes ===")
    print(df["task_outcome"].value_counts().to_string())

    print("\n=== Deadline Performance ===")
    print(f"Deadline misses: {df['deadline_missed'].sum()}")
    print(
        "Deadline miss rate: "
        f"{df['deadline_missed'].mean() * 100:.2f}%"
    )

    print("\n=== Fallback ===")
    print(f"Rows with fallback active: {df['fallback_active'].sum()}")
    print(
        "Fallback-active rate: "
        f"{df['fallback_active'].mean() * 100:.2f}%"
    )

    print("\n=== Timing Statistics (ms) ===")
    for column in [
        "execution_time_ms",
        "response_time_ms",
        "message_age_ms",
    ]:
        print(f"\n{column}:")
        print(df[column].describe().round(2).to_string())

    print("\n=== Deadline Misses by Scenario ===")
    scenario_stats = (
        df.groupby("scenario_label")["deadline_missed"]
        .agg(["count", "sum", "mean"])
        .rename(columns={
            "count": "records",
            "sum": "deadline_misses",
            "mean": "miss_rate",
        })
    )
    scenario_stats["miss_rate_pct"] = scenario_stats["miss_rate"] * 100
    print(
        scenario_stats.drop(columns="miss_rate")
        .round(2)
        .to_string()
    )

    print("\n=== Task Outcomes by Scenario ===")
    print(pd.crosstab(
        df["scenario_label"],
        df["task_outcome"],
    ).to_string())

    # Plot deadline-miss rate for each scenario.
    chart_data = scenario_stats["miss_rate_pct"].sort_values(
        ascending=False
    )

    plt.figure(figsize=(9, 5))
    bars = plt.bar(
        chart_data.index,
        chart_data.values,
    )
    plt.title("Deadline-Miss Rate by Scenario")
    plt.xlabel("Scenario")
    plt.ylabel("Deadline-Miss Rate (%)")
    plt.xticks(rotation=25, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.4)

    for bar, value in zip(bars, chart_data.values):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.2f}%",
            ha="center",
            va="bottom",
        )

    plt.tight_layout()
    chart_path = OUTPUT_DIR / "deadline_miss_by_scenario.png"
    plt.savefig(chart_path, dpi=200)
    plt.close()

    print(f"\nChart saved to: {chart_path}")


if __name__ == "__main__":
    main()