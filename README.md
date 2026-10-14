# Security-Aware Real-Time Sensor Scheduling System

A machine-learning-assisted security and scheduling prototype for real-time sensor systems.

## Overview

Real-time systems process data from sensors under timing constraints. Unauthenticated, replayed, anomalous, or late messages can reduce the reliability of downstream decisions.

This project combines message authentication, replay protection, rule-based sensor checks, a trained machine-learning model, and deadline-aware task scheduling. A Streamlit dashboard supports dataset analysis and interactive testing of sensor-message scenarios.

> **Scope:** This is an academic simulation prototype. It is not a hard real-time operating-system implementation and is not certified for safety-critical deployment.

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

- HMAC-SHA256 message authentication using configured shared demo keys.
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
HMAC authentication and sequence/replay checks
      |
      v
Input validation and feature extraction
      |
      v
Rule-based sensor checks + ML classification
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

The current sensor-pipeline test suite contains 10 tests. The latest run reported **10 passed, 0 failed**. Coverage includes valid messages, tampering, replay protection, out-of-range readings, unknown sensors, ML anomaly rejection, deadline misses, and ensuring rejected or late readings do not update accepted-reading history.

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
- Compare EDF with alternative real-time scheduling strategies.
- Measure authentication and inference overhead under controlled workloads.
- Add overload and burst-arrival stress tests.
- Integrate a validated safe-state interface where appropriate.
- Add experiment logging and exportable reports.

## Conclusion

This project demonstrates an academic prototype combining cryptographic message authentication, sensor-health classification, and deadline-aware scheduling. It explores how security checks and anomaly detection can affect the processing of real-time sensor tasks and how fallback behavior can respond when timing constraints cannot be satisfied.

The implementation is intended for academic experimentation and further research, not direct deployment in safety-critical environments.

```
