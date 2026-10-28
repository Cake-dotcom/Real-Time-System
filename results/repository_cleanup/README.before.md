# Security-Aware Real-Time Sensor Scheduling System

A machine-learning-assisted security and scheduling prototype for real-time sensor systems.

## Interactive scheduling laboratory

Launch the upgraded five-tab workload designer, security monitor, trace playback,
results and algorithm-comparison laboratory:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

The default **15-second, four-sensor workload** is editable. Add/duplicate/delete
tasks, configure periodic/sporadic arrivals, phases, tampering, genuine replay,
sensor conditions and timed risk changes, then select **Run laboratory**. Choose
**Tampered and replayed → Load preset** for an immediate security demonstration.
The event slider and Gantt chart replay actual scheduler output. CSV/JSON exports
and repeated authenticated seeded comparisons are available in the tabs.

Vehicle examples explicitly use the retained RF baseline. GRU remains available
and fails closed without SKAB features and trusted context. The existing dashboard
and all security gates remain accessible. See [usage, presets, architecture and
limitations](docs/laboratory.md) and [actual laboratory results](results/laboratory/report.md).
The final upgrade passed **235 tests**; see the [delivery evidence and remaining
limitations](docs/laboratory_delivery.md).

```powershell
.\.venv\Scripts\python.exe -u scripts/evaluate_laboratory.py
```

## Risk-aware limited-preemption scheduler

The project now includes an event-driven **RA-LP-EDF simulator** with periodic and
sporadic jobs, fixed phase preemption points, explicit transition costs, critical
reservations, admission/overload handling, risk freshness, mandatory protection
levels and safe-stop behavior. Select **RA-LP-EDF** in the dashboard's **Live
scheduling algorithm** control to invoke it after the real authentication and
health gates. The default legacy path remains compatible with earlier scenarios.
The scheduling laboratory runs reproducible recurring synthetic workloads.

See the [algorithm, exact reference sections and assumptions](docs/scheduling_design.md),
[requirement status and implementation inventory](docs/scheduling_completion.md),
and [measured comparisons and limitations](results/scheduling/evaluation_report.md).
Configured costs are synthetic; static analysis and finite admission checks do
not establish an infinite dynamic-risk or deployment-level timing guarantee.

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -u -m src.scheduler.experiments --full --workers 4
.\.venv\Scripts\python.exe scripts/report_scheduling.py
```

The active sensor-health backend now uses a trained **GRU on Skoltech Anomaly Benchmark (SKAB)**.
See [model protocol and runtime integration](docs/gru_sensor_model.md),
[measured evaluation](results/gru/evaluation_report.md), and
[dataset provenance](data/SKAB_DATASET.md). The vehicle Random Forest remains an
explicit baseline option. GRU requires actual SKAB-domain features and trusted
startup context; distance-only vehicle inputs fail closed. Authentication, replay,
risk-policy and scheduler gates remain mandatory. The GRU is faster in the measured
CPU benchmark but has lower held-out macro-F1 than the refitted SKAB RF baseline.

## Overview

Real-time systems process data from sensors under timing constraints. Unauthenticated, replayed, anomalous, or late messages can reduce the reliability of downstream decisions.

This project combines message authentication, replay protection, rule-based sensor checks, a trained machine-learning model, and deadline-aware task scheduling. A Streamlit dashboard supports dataset analysis and interactive testing of sensor-message scenarios.

The live pipeline now applies **NIST SP 800-30 Rev. 1, §3.2 Task 2-6 and Appendix I Table I-2** to combine project-defined likelihood and impact evidence. OT response context comes from **NIST SP 800-82 Rev. 3 §§4.1.2–4.1.3**. See [the integrated policy](docs/risk_validation_policy.md) and [research/design note](docs/policy_research_note.md) for official URLs, exact sections, assumptions, response choices and limitations. NIST does not prescribe our sensor thresholds, validation costs or EDF algorithm.

> **Scope:** This is an academic simulation prototype. It is not a hard real-time operating-system implementation and is not certified for safety-critical deployment.

## Source authentication and session reuse

The receiver now requires a short-lived authenticated source session before accepting any sensor message. A sensor proves possession of its provisioned secret using HMAC-SHA256 over a random challenge bound to its identity and the receiver's boot context. Successful authentication establishes a random session ID and a separately derived message key. Challenges expire after 5 seconds and sessions after 60 seconds, using a monotonic clock.

**Session reuse never skips per-message verification.** Every message MAC covers its source, session ID, sequence and full contents using canonical serialization. The receiver checks session validity, MAC and a strictly increasing source-wide sequence. Replay counters survive reauthentication. Session revocation, source compromise revocation, administrative key rotation, reset/restart rejection and bounded cleanup are implemented. Expired/revoked sessions fail closed; the dashboard supports explicit reauthentication and displays actual receiver state/counters.

Threat model: an attacker may inject, tamper with, replay or reorder messages; the receiver, clock, provisioned key map and administrative operations are trusted. A stolen sensor secret permits impersonation until source revocation/key rotation. Keys are simulated, state is in memory, and production restart must reload revoked identities. No encryption, forward secrecy, mutual receiver authentication, wire transport or production automotive key management is claimed. The shared-state dashboard is a local demonstration, not an authenticated administration service.

The scheduler's per-message `security_overhead` already includes MAC verification. A new session adds **2 simulated units once**, on its first successfully verified message, plus the selected validation cost (0/1/2). Reuse adds zero handshake units, while the MAC check still runs. Measured nanoseconds are reported separately and never inserted into EDF costs. The 2-unit handshake cost is an uncalibrated project parameter. CPU work spent rejecting traffic or checking deferred tasks is not modeled as scheduler demand.

See [protocol, lifecycle and methodology](docs/source_authentication.md) and [actual verification results](docs/source_auth_verification.md). These supersede the earlier policy-only timing examples.

### Earlier source-session verification and benchmark

**99 tests passed in 16.88 seconds** on 2026-10-27, including session security, accepted-history invariants, all original scenarios, real Streamlit form/lifecycle tests and the repaired legacy login coordinator. No dependencies or model artifacts were changed.

Benchmark: 10 alternating paired repetitions, each with 1,000 valid messages, 50 replays and 50 tampered messages across three sensors. Both approaches use the same payloads, MAC verification and source-wide replay policy. The baseline repeats the new source handshake for every message; it is not the previous bare-HMAC implementation. Warmup is excluded.

| Measured quantity | Full authentication each message | Session reuse |
|---|---:|---:|
| Full handshakes | 11,000 | 30 |
| MAC verifications | 11,000 | 11,000 |
| Exchange mean / median / p95 (µs) | 72.85 / 70.10 / 89.20 | 23.91 / 22.80 / 27.50 |
| Receiver mean / median / p95 (µs) | 41.27 / 39.60 / 49.20 | 13.42 / 12.80 / 13.90 |
| Total measured receiver authentication (ms) | 453.94 | 147.58 |
| Total measured loop elapsed time (ms) | 811.84 | 271.47 |
| Accepted injected attacks | 0 | 0 |

Receiver authentication time was **67.49% lower in this run**. This is a local in-process Python measurement, not network/ECU latency or a hard-real-time bound. `perf_counter_ns` measures elapsed time; separate process CPU totals and per-repetition means are saved in `results/source_auth/benchmark.json`.

The 40-message policy comparison uses the same mandatory source/MAC/replay/health gates in all modes. Base EDF / fixed / adaptive accepted 5 / 3 / 4 messages, missed 6 / 7 / 7 scheduled deadlines, deferred 4 / 5 / 4 messages, and accepted **zero mandatory-security violations**. Scheduled total security overhead was 33 / 50 / 43 simulated units. Full counts and denominators are in `results/source_auth/policy_comparison.json`; this toy workload does not establish broad superiority.

Reproduce from the project directory with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
.\.venv\Scripts\python.exe -m src.ml.benchmark_source_auth --messages 1000 --repetitions 10
.\.venv\Scripts\python.exe -m src.ml.compare_validation_policies
.\.venv\Scripts\python.exe -m src.ml.evaluate_sensor_model --all-runs --output-dir results/source_auth
.\.venv\Scripts\python.exe -m src.security.security_system
```

## Objectives

- Authenticate messages with HMAC-SHA256.
- Reject tampered, replayed, out-of-order, and unknown-sensor messages.
- Validate sensor readings and detect sudden changes.
- Use a Random Forest model to classify readings as `normal`, `anomalous_reading`, or `faulty`.
- Simulate deadline-aware scheduling while accounting for execution time and security overhead.
- Defer non-critical tasks when the scheduler enters fallback mode.
- Avoid committing rejected or deadline-missed readings to accepted-reading history.
- Visualize dataset, sensor-health, and scheduling results in a dashboard.

## Main Features

### Message authentication and replay protection

- Challenge-response source authentication using provisioned demo keys, then HMAC-SHA256 per-message authentication with session-derived keys.
- Constant-time MAC comparison.
- Per-sensor sequence tracking to reject duplicate and out-of-order messages.

### Sensor-health monitoring

- Sensor ID and reading-range validation.
- Rule-based detection of sudden changes in accepted readings.
- ML predictions for normal, anomalous, and faulty readings.
- Feature extraction using sensor metadata, sequence changes, message age, reading statistics, and MAC verification status.

### Machine learning

The sensor-health model is trained by `src/ml/train_sensor_model.py` using a Random Forest classifier and a preprocessing pipeline for numeric and categorical features. Evaluation uses a group-based split by `run_id` to reduce leakage between records from the same run.

### Deadline-aware scheduling and fallback

The scheduler in `src/scheduler/scheduler.py` simulates non-preemptive Earliest Deadline First (EDF) scheduling. It considers task arrival time, execution time, security overhead, and deadline.

The pipeline reports scheduling modes including:

- `ALL_SENSORS` — all eligible tasks meet their deadlines.
- `CRITICAL_ONLY` — critical tasks meet their deadlines while non-critical work is deferred.
- `CRITICAL_DEADLINE_FAILURE` — critical task deadlines cannot be met.
- `NO_VALID_TASKS` — no eligible tasks are available.

The system emits a software safety-response message for relevant failure modes. Actual safe-state actuation is not implemented.

### Streamlit dashboard

The dashboard in `src/dashboard/app.py` provides dataset summaries, scenario deadline-miss analysis, sensor-health and authentication summaries, timing statistics, record inspection, and a live simulator for valid, tampered, and replayed messages. The simulator supports resetting its state for repeatable experiments.

## Architecture

```text
Sensor message
      |
      v
Authenticated source session (challenge-response, expiry/revocation)
      |
      v
HMAC authentication and sequence/replay checks
      |
      v
Input validation and feature extraction
      |
      v
Rule-based sensor checks + ML classification
      |
      v
Likelihood/impact assessment (NIST Table I-2)
      |
      v
Required additional checks + fail-closed policy response
      |
      v
Eligible sensor tasks
      |
      v
Deadline-aware EDF scheduling
      |
      +---- Normal scheduling
      |
      +---- Critical-only fallback / deadline-failure response
      |
      v
Final acceptance decision and dashboard results
```

Sensor feature history and health history are committed only after final acceptance. Rejected messages and tasks that miss deadlines should not update accepted-reading history.

Authentication/replay failures exit before policy evaluation. Missing model/evidence prevents acceptance. Healthy messages must pass selected checks and meet their deadline. The dashboard displays the backend decision and per-check audit. Normal critical sensors receive additional validation (1 simulated unit); normal camera readings use standard plausibility checks (0 extra units). All thresholds and 0/1/2 costs are centralized in `src/security/validation_config.py` and are project assumptions. Scheduler deadlines are absolute, and scheduler times are abstract simulation units.

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Machine learning | scikit-learn |
| Data processing | pandas, NumPy |
| Model persistence | joblib |
| Dashboard | Streamlit |
| Visualization | Matplotlib and Streamlit displays |
| Message authentication | HMAC-SHA256 |
| Testing | pytest |

## Project Structure

```text
Real time systems project/
├── data/
│   ├── raw/
│   │   ├── av_sensor_messages.csv
│   │   └── login_activity.csv              # legacy dataset, if retained
│   └── processed/
├── models/
│   └── sensor_health_model.joblib
├── results/
│   ├── deadline_miss_by_scenario.png
│   └── sensor_model_report.txt
├── src/
│   ├── dashboard/
│   │   └── app.py
│   ├── ml/
│   │   ├── evaluate_sensor_dataset.py
│   │   ├── train_sensor_model.py
│   │   ├── validate_dataset.py             # older/general validator
│   │   └── validate_sensor_dataset.py
│   ├── scheduler/
│   │   └── scheduler.py
│   └── security/
│       ├── auth_policy.py                  # legacy login-risk code
│       ├── message_auth.py
│       ├── message_monitor.py
│       ├── risk_engine.py                  # legacy login-risk code
│       ├── security_system.py               # legacy login-risk code
│       ├── sensor_features.py
│       ├── sensor_health.py
│       └── sensor_system.py
├── tests/
│   ├── test_sensor_system.py
│   └── test_setup.py
├── .gitignore
└── README.md
```

`__pycache__`, `.pytest_cache`, and `.venv` are local/generated directories and should normally not be committed. The login-risk scripts and `login_activity.csv` are retained legacy files; the current sensor pipeline uses the sensor-specific scripts listed above.

## Dataset

The main dataset is `data/raw/av_sensor_messages.csv`. The current dataset version contains 20,629 records and 31 columns covering sensor readings, sequence information, authentication flags, timing measurements, scheduling outcomes, and labels.

Scenario labels include normal operation, overload, tampering, replay, and sensor fault. Sensor-health labels are `normal`, `anomalous_reading`, and `faulty`. Sensor types in the dataset include LiDAR, radar, camera, GPS, IMU, and ultrasonic. The live simulator currently demonstrates `LIDAR_01`, `RADAR_01`, and `CAMERA_01`.

## Setup
### 3. Install Dependencies

Install all required Python packages from the repository's `requirements.txt` file:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The `requirements.txt` file contains the Python dependencies used by the project.

## Running the Project

Run the following commands from the project root directory.

### Launch the Dashboard

```powershell
python -m streamlit run src/dashboard/app.py
```

Open the local URL displayed in the terminal, usually `http://localhost:8501`.

### Run the Tests

```powershell
python -m pytest -v
```

### Train the Sensor-Health Model

```powershell
python -m src.ml.train_sensor_model
```

Training generates the model artifact under `models/`. You can skip this step if the pre-trained `models/sensor_health_model.joblib` file is already available.

### Prerequisites

- Python 3.12 or a compatible version
- pip
- The project dataset at `data/raw/av_sensor_messages.csv`

### Clone the repository

```bash
git clone https://github.com/Cake-dotcom/Real-Time-System.git
cd Real-Time-System
```

If you already have the project open in VS Code, run the commands below from the project root instead.

### Create and activate a virtual environment (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install pandas numpy scikit-learn matplotlib streamlit joblib pytest
```

## Run the Project

Run these commands from the repository root.

### Start the dashboard

```powershell
python -m streamlit run src/dashboard/app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

### Train the sensor-health model

```powershell
python -m src.ml.train_sensor_model
```

This trains and saves `models/sensor_health_model.joblib` and writes the model evaluation report to `results/sensor_model_report.txt` (as configured by the training script).

### Validate the sensor dataset

```powershell
python -m src.ml.validate_sensor_dataset
```

### Evaluate the dataset

```powershell
python -m src.ml.evaluate_sensor_dataset
```

The evaluation script reports dataset and deadline statistics and generates `results/deadline_miss_by_scenario.png`.

### Run the sensor-system demonstration

```powershell
python -m src.security.sensor_system
```

### Run all tests

```powershell
python -m pytest -v
```

### Check Python syntax

```powershell
python -m compileall -q src tests
```

## Tests

The suite includes the original sensor/policy tests, `tests/test_source_sessions.py`, backend integration tests in `tests/test_policy_integration.py`, and Streamlit form tests in `tests/test_dashboard_policy.py`. These exercise source lifecycle, permissive-policy bypass attempts, evidence selection, executed checks, missing evidence, authentication/validation cost-caused misses, history preservation, and dashboard/backend correspondence. See `docs/source_auth_verification.md` for the current run; `docs/policy_verification.md` preserves the earlier policy-only run.

Re-run the tests after changing code; the result reported here describes the latest run available when this README was prepared and may not reflect future changes.

## Preliminary Results

The reported held-out-run model evaluation produced the following results:

| Metric | Result |
|---|---:|
| Accuracy | 99.04% |
| Balanced accuracy | 89.91% |
| Normal-class F1-score | 1.00 |
| Anomalous-reading F1-score | 0.98 |
| Faulty-class F1-score | 0.72 |

These are preliminary results from a dataset with only four distinct runs. The `faulty` class is more difficult to detect, so overall accuracy alone is not sufficient to establish model reliability.

The new four-fold leave-one-run-out evaluation shows considerably weaker fault detection on other runs:

| Held-out run | Accuracy | Balanced accuracy | Faulty F1 |
|---|---:|---:|---:|
| 0 | 0.9775 | 0.7197 | 0.2302 |
| 1 | 0.9904 | 0.8991 | 0.7215 |
| 2 | 0.9807 | 0.7242 | 0.2636 |
| 3 | 0.9765 | 0.7113 | 0.3125 |

Run 1 was the original single holdout. Full per-class metrics/confusion matrices are in `results/source_auth/sensor_model_evaluation.json`. The saved artifact agrees with the fresh refit on that reconstructed holdout, but lacks stored split provenance. Accuracy is not evidence of system security or generalization. All evaluation refits stay in memory and preserve the saved model.

The grouped evaluation was reproduced with an in-memory refit, preserving the existing model artifacts. Full per-class metrics, confusion matrix, split IDs and hashes are in `results/policy_evaluation/sensor_model_evaluation.json`. Reproduce it and the small synthetic baseline/fixed/adaptive comparison with:

```powershell
.\.venv\Scripts\python.exe -m src.ml.evaluate_sensor_model
.\.venv\Scripts\python.exe -m src.ml.compare_validation_policies
```

The comparison uses identical signed inputs and the real backend/model. Its results illustrate assumed validation costs; they do not establish real-world security or performance improvements. Rejection CPU work is not modeled. Outcomes grouped by health are model predictions, not independently labeled classes.

The dataset evaluation reported 586 deadline misses among 20,629 records (approximately 2.84%). These are dataset-derived statistics, not measured performance guarantees for a production real-time system.

## Limitations

- Scheduling is simulated in Python; this is not a hard real-time operating-system scheduler.
- The live simulator uses synthetic messages and demonstration keys.
- The dataset has only four distinct runs, limiting the strength of grouped evaluation.
- Model performance may not generalize to real-world sensor data.
- Sensor-specific units and features require further validation before extending the live pipeline to all sensor types.
- The safe-state response is a software message, not an integrated safety controller.
- The prototype is not certified or validated for deployment in autonomous vehicles or other safety-critical systems.

## Future Work

- Collect more diverse sensor data and evaluate on additional independent runs.
- Improve detection of the `faulty` class.
- Implement and validate sensor-specific feature extraction for GPS, IMU, and ultrasonic data.
- Extend the measured scheduler comparisons with faithful published baselines and deployment cost bounds.
- Measure authentication and inference overhead on representative sensor/ECU hardware; the current benchmark measures local authentication only.
- Extend overload experiments to bursty threat traffic and recurring critical-server reservations.
- Integrate a validated safe-state interface where appropriate.
- Extend the saved scheduler experiment reports with hardware measurements.

## Conclusion

This project demonstrates an academic prototype combining cryptographic message authentication, sensor-health classification, and deadline-aware scheduling. It explores how security checks and anomaly detection can affect the processing of real-time sensor tasks and how fallback behavior can respond when timing constraints cannot be satisfied.

The implementation is intended for academic experimentation and further research, not direct deployment in safety-critical environments.

```
## Scheduler optimization

Optional admission, limited-preemption and combined optimization modes are available in the existing laboratory. The original RA-LP-EDF remains the default. See [the optimization delivery](docs/scheduler_optimization.md) for the paired 20-seed results, security tests, exact run commands, side-by-side dashboard comparison and the documented unexpected-risk trade-off.
