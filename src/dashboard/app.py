import sys
from pathlib import Path

# Add the project root to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import copy
import pandas as pd
import streamlit as st

from src.security import sensor_system
from src.security.source_sessions import authenticate_sender, AuthenticationError
from src.security.sensor_health import SensorHealthMonitor
from src.security.gru_health import GRUHealthMonitor

st.set_page_config(
    page_title="Real-Time Sensor Security Dashboard",
    page_icon="🛡️",
    layout="wide",
)

DATASET = Path("data/raw/av_sensor_messages.csv")
CHART = Path("results/deadline_miss_by_scenario.png")


# ============================================================
# Dashboard Header
# ============================================================

st.title("Real-Time Sensor Security and Scheduling Dashboard")
st.caption(
    "Dataset-driven analysis of message authentication, sensor health, "
    "deadline performance, and fallback behavior."
)

from src.dashboard.laboratory import show_laboratory
show_laboratory()
st.divider()
st.header("Existing sensor dashboard and benchmark tools")


# ============================================================
# Load Dataset
# ============================================================

if not DATASET.exists():
    st.error(f"Dataset not found: {DATASET}")
    st.stop()

df = pd.read_csv(DATASET)

required_columns = [
    "scenario_label",
    "sensor_id",
    "deadline_missed",
    "mac_verified",
    "fallback_active",
    "sensor_health_label",
    "task_outcome",
    "execution_time_ms",
    "response_time_ms",
    "message_age_ms",
]

missing_columns = [
    column for column in required_columns
    if column not in df.columns
]

if missing_columns:
    st.error(f"Missing required columns: {missing_columns}")
    st.stop()


# ============================================================
# Sidebar Filters
# ============================================================

st.sidebar.header("Filters")
live_scheduler = st.sidebar.selectbox("Live scheduling algorithm", ["legacy", "RA-LP-EDF"])

scenarios = sorted(
    df["scenario_label"].dropna().unique().tolist()
)

selected_scenarios = st.sidebar.multiselect(
    "Scenarios",
    scenarios,
    default=scenarios,
)

sensors = sorted(
    df["sensor_id"].dropna().unique().tolist()
)

selected_sensors = st.sidebar.multiselect(
    "Sensors",
    sensors,
    default=sensors,
)

filtered = df[
    df["scenario_label"].isin(selected_scenarios)
    & df["sensor_id"].isin(selected_sensors)
].copy()

if filtered.empty:
    st.warning("No records match the selected filters.")
    st.stop()


# ============================================================
# Dataset Overview
# ============================================================

st.header("Dataset Overview")

total = len(filtered)
deadline_misses = int(filtered["deadline_missed"].sum())
mac_rejected = int((filtered["mac_verified"] == 0).sum())
fallback_rows = int(filtered["fallback_active"].sum())

c1, c2, c3, c4 = st.columns(4)

c1.metric("Messages", f"{total:,}")

c2.metric(
    "Deadline-miss rate",
    f"{filtered['deadline_missed'].mean() * 100:.2f}%",
    help=f"{deadline_misses:,} deadline misses in the filtered records",
)

c3.metric(
    "MAC-rejected records",
    f"{mac_rejected:,}",
    help="Records where the dataset's mac_verified field is 0",
)

c4.metric(
    "Fallback-active records",
    f"{fallback_rows:,}",
    f"{filtered['fallback_active'].mean() * 100:.2f}% of filtered records",
)


# ============================================================
# Deadline Performance by Scenario
# ============================================================

st.header("Deadline Performance by Scenario")

scenario_stats = (
    filtered.groupby("scenario_label")
    .agg(
        records=("deadline_missed", "size"),
        deadline_misses=("deadline_missed", "sum"),
        miss_rate=("deadline_missed", "mean"),
    )
    .sort_values("miss_rate", ascending=False)
)

scenario_stats["Miss rate (%)"] = scenario_stats["miss_rate"] * 100

st.bar_chart(scenario_stats["Miss rate (%)"])

st.dataframe(
    scenario_stats[
        ["records", "deadline_misses", "Miss rate (%)"]
    ].round(2),
    use_container_width=True,
)

if CHART.exists():
    st.subheader("Full-Dataset Scenario Comparison")
    st.image(
        str(CHART),
        caption="Deadline-miss rates from the complete dataset",
        use_container_width=True,
    )


# ============================================================
# Authentication and Sensor Health
# ============================================================

left, right = st.columns(2)

with left:
    st.header("Message Authentication")

    auth_counts = (
        filtered["mac_verified"]
        .map({0: "MAC rejected", 1: "MAC verified"})
        .fillna("Unknown")
        .value_counts()
    )

    st.bar_chart(auth_counts)

    st.dataframe(
        auth_counts.rename_axis("Authentication result")
        .reset_index(name="Records"),
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.header("Sensor Health")

    health_counts = filtered["sensor_health_label"].value_counts()

    st.bar_chart(health_counts)

    st.dataframe(
        health_counts.rename_axis("Health label")
        .reset_index(name="Records"),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# Scheduling and Fallback Analysis
# ============================================================

st.header("Scheduling and Fallback Analysis")

outcomes = pd.crosstab(
    filtered["scenario_label"],
    filtered["task_outcome"],
)

st.subheader("Task outcomes by scenario")
st.bar_chart(outcomes)
st.dataframe(outcomes, use_container_width=True)

fallback_by_scenario = (
    filtered.groupby("scenario_label")["fallback_active"]
    .agg(["sum", "mean"])
    .rename(
        columns={
            "sum": "Fallback-active records",
            "mean": "Fallback rate",
        }
    )
)

fallback_by_scenario["Fallback rate (%)"] = (
    fallback_by_scenario.pop("Fallback rate") * 100
)

st.subheader("Fallback activity by scenario")

st.bar_chart(fallback_by_scenario["Fallback rate (%)"])

st.dataframe(
    fallback_by_scenario.round(2),
    use_container_width=True,
)


# ============================================================
# Timing Statistics
# ============================================================

st.header("Timing Statistics")

timing_columns = [
    "execution_time_ms",
    "response_time_ms",
    "message_age_ms",
]

st.dataframe(
    filtered[timing_columns].describe().round(2),
    use_container_width=True,
)


# ============================================================
# Inspect Dataset Records
# ============================================================

with st.expander("Inspect individual dataset records"):
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    "Interpretation note: this dashboard displays outcomes and labels "
    "already recorded in the dataset. It does not independently verify "
    "message MACs or reproduce the live scheduler's decisions."
)


# ============================================================
# Live Sensor Security Simulator
# ============================================================

st.divider()
st.header("Live Sensor Security Simulator")
model_options = ["GRU / SKAB", "Random Forest / vehicle baseline"]
active_model = getattr(sensor_system.health_monitor, "model_name", "Custom health monitor")
model_choice = st.selectbox("Sensor-health model", model_options,
                           index=1 if active_model == model_options[1] else 0)
if model_choice != active_model and active_model in model_options:
    sensor_system.health_monitor = GRUHealthMonitor() if model_choice == model_options[0] else SensorHealthMonitor()
    sensor_system.feature_tracker.reset()
st.write(f"Active sensor-health model: {getattr(sensor_system.health_monitor, 'model_name', 'Custom')}")
if model_choice == model_options[0]:
    st.caption("GRU requires eight SKAB water-testbed measurements and commissioned temporal context. "
               "Vehicle distance-only submissions fail closed. The RF option retains the vehicle baseline.")
    with st.expander("Authenticated SKAB recording demonstration"):
        st.write("This administrative demonstration commissions context from the checksum-verified local "
                 "nominal SKAB recording, binds it to a new session, then processes one signed candidate "
                 "through all security, policy and scheduling gates. It does not claim vehicle accuracy.")
        if st.button("Commission and process one recorded SKAB sample"):
            try:
                from src.ml.replay_skab_gru import commission_and_process
                demonstration = commission_and_process(sensor_system)
                st.json(demonstration)
            except Exception:
                st.error("SKAB demonstration unavailable; no acceptance reported. Check artifact and local dataset.")

st.write(
    "Submit a sensor message to the existing authentication, "
    "sensor-health, NIST-based risk assessment, and deadline-aware scheduling pipeline."
)
st.caption(
    "Risk assessment: NIST SP 800-30 Rev. 1, §3.2 Task 2-6 / Table I-2. "
    "Sensor mappings and validation costs are project-defined. All scheduler "
    "times and overheads are simulated units, not measured milliseconds."
)
if st.button("Reset simulation state"):
    sensor_system.message_monitor.sessions.reset()
    st.session_state.pop("sensor_senders", None)
    sensor_system.health_monitor.reset()
    sensor_system.feature_tracker.reset()
    st.success("Simulation state reset.")
    st.rerun()

manager = sensor_system.message_monitor.sessions
if st.session_state.get("receiver_context") != manager.receiver_context:
    st.session_state.sensor_senders = {}
    st.session_state.receiver_context = manager.receiver_context
senders = st.session_state.setdefault("sensor_senders", {})
session_source = st.selectbox("Session source", list(sensor_system.SENSOR_KEYS))
if st.button("Authenticate / reauthenticate source"):
    try:
        senders[session_source] = authenticate_sender(
            manager, session_source, sensor_system.SENSOR_KEYS[session_source])
        st.success("Source authentication succeeded.")
    except AuthenticationError:
        st.error("Source authentication failed. Check revocation and provisioning status.")
if st.button("Revoke source session"):
    manager.revoke_session(session_source)
if st.button("Flag source credential compromise"):
    manager.revoke_source(session_source)
st.caption("The first submission authenticates the simulated sensor. Expired or revoked "
           "sessions require explicit reauthentication; a compromised source requires key rotation. "
           "Every message still receives MAC and replay verification.")

with st.form("sensor_simulator"):
    selected_sensor = st.selectbox(
        "Sensor",
        ["LIDAR_01", "RADAR_01", "CAMERA_01"],
    )

    sequence = st.number_input(
        "Sequence number",
        min_value=1,
        value=1,
        step=1,
    )

    distance = st.number_input(
        "Distance reading (m)",
        min_value=-1000.0,
        max_value=1000.0,
        value=12.0,
        step=1.0,
    )
    message_age_ms = st.number_input(
        "Message age (ms)",
        min_value=0.0,
        max_value=60000.0,
        value=5.0,
        step=1.0,
    )

    attack = st.selectbox(
        "Simulation mode",
        [
            "Valid message",
            "Tampered message",
            "Replay previous message",
        ],
    )

    arrival = st.number_input(
        "Arrival time",
        min_value=0,
        value=0,
        step=1,
    )

    execution = st.number_input(
        "Execution time",
        min_value=1,
        value=3,
        step=1,
    )

    overhead = st.number_input(
        "Per-message security overhead (includes MAC verification; simulated units)",
        min_value=0,
        value=1,
        step=1,
    )

    deadline = st.number_input(
        "Absolute deadline (simulation units)",
        min_value=1,
        value=10,
        step=1,
    )

    submitted = st.form_submit_button(
        "Process Sensor Message",
        type="primary",
    )


# ============================================================
# Process Submitted Sensor Message
# ============================================================

if submitted:
    message = {
        "sensor_id": selected_sensor,
        "sequence": int(sequence),
        "timestamp": 1000,
        "distance_m": float(distance),
    }

    if selected_sensor not in senders:
        try:
            senders[selected_sensor] = authenticate_sender(
                manager, selected_sensor, sensor_system.SENSOR_KEYS[selected_sensor])
        except AuthenticationError:
            st.error("Source authentication failed; no message was submitted.")
            st.stop()
    message, mac = senders[selected_sensor].sign(message)

    # Prepare the selected simulation scenario.
    if attack == "Tampered message":
        # Change the message after generating its MAC.
        message["distance_m"] = float(distance) + 1.0

    if attack == "Replay previous message":
        # Submit the same authenticated message twice.
        replay_message = copy.deepcopy(message)
        replay_mac = mac

        messages = [
            {
                "message": message,
                "mac": mac,
                "arrival_time": int(arrival),
                "execution_time": int(execution),
                "security_overhead": int(overhead),
                "deadline": int(deadline),
                "message_age_ms": float(message_age_ms),
            },
            {
                "message": replay_message,
                "mac": replay_mac,
                "arrival_time": int(arrival) + 1,
                "execution_time": int(execution),
                "security_overhead": int(overhead),
                "deadline": int(deadline) + 1,
                "message_age_ms": float(message_age_ms),
            },
        ]

    else:
        messages = [
            {
                "message": message,
                "mac": mac,
                "arrival_time": int(arrival),
                "execution_time": int(execution),
                "security_overhead": int(overhead),
                "deadline": int(deadline),
                "message_age_ms": float(message_age_ms),
            }
        ]


    # Send messages through the existing pipeline.
    try:
        result = (sensor_system.process_messages(messages) if live_scheduler == "legacy" else
                  sensor_system.process_messages(messages, scheduling_algorithm=live_scheduler))

        st.subheader("Message Decisions")
        st.write(f"Measured application processing: {result['application_processing_ms']:.3f} ms")

        st.dataframe(
            result["messages"],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Backend policy and validation audit")
        for index, decision in enumerate(result["messages"], start=1):
            with st.expander(f"Message {index}: {decision['sensor']} — {decision['status']}"):
                st.json(decision)

        st.subheader("Scheduling Result")
        if "research" in result["schedule"]:
            from src.dashboard.scheduling_panel import show_trace
            show_trace(result["schedule"]["research"])

        st.write(f"**Mode:** {result['schedule']['mode']}")
        st.write(
            f"**Safety response:** {result['safety_response']}"
        )

        if result["schedule"]["results"]:
            st.dataframe(
                result["schedule"]["results"],
                use_container_width=True,
                hide_index=True,
            )

        if result["schedule"]["deferred_sensors"]:
            st.warning(
                "Deferred task IDs: "
                + ", ".join(
                    map(
                        str,
                        result["schedule"]["deferred_sensors"],
                    )
                )
            )

    except Exception:
        st.error("Message processing unavailable; no acceptance is reported.")

st.subheader("Source sessions and measured authentication overhead")
st.dataframe(manager.public_status(), hide_index=True)
st.dataframe([dict(manager.metrics)], hide_index=True)
st.caption("Counters come from the receiver. *_ns values are measured elapsed processing "
           "nanoseconds, not scheduler costs. A new session adds 2 simulated units on "
           "its first verified message; reuse adds no handshake cost.")

from src.dashboard.scheduling_panel import show_experiments
show_experiments()
