# Implementation verification — 2026-10-27

Historical policy-only verification. The later session-authentication extension,
new timing results, and repaired legacy login wrapper are reported in
[source_auth_verification.md](source_auth_verification.md).

## Result

The sensor risk policy is integrated into the live dashboard backend. The full
suite completed with **64 passed in 41.96 seconds**, including all 30 original
tests. Python is 3.12.6 in the existing `.venv`; no dependencies were added.

Official provenance and project assumptions are recorded in
[risk_validation_policy.md](risk_validation_policy.md) and
[policy_research_note.md](policy_research_note.md). The selected foundation is
NIST SP 800-30 Rev. 1 §3.2 Task 2-6 and Appendix I Table I-2, with OT context
from NIST SP 800-82 Rev. 3 §§4.1.2–4.1.3.

## Integration evidence

`src/dashboard/app.py` calls `sensor_system.process_messages`; the coordinator
enforces HMAC/replay and input validation, builds health evidence, invokes
`assess_sensor_risk`, executes `validate_additional_checks`, adds extra cost once,
and runs EDF. Acceptance and history commits follow a met deadline. The dashboard
renders the actual backend decision and check results in its audit expander.

`test_permissive_policy_cannot_bypass_security_gates` tests invalid MAC and replay
on camera inputs that otherwise produce low risk. It installs a permissive policy
and confirms policy, extra-check and scheduler functions are never called, the
message is rejected, and accepted/replay histories are unchanged.

`test_dashboard_runs_backend_and_displays_actual_policy` submits valid, tampered
and replay form choices with Streamlit AppTest. It wraps the real policy and
compares rendered JSON with captured backend decisions. Other integration tests
cover low/medium/high checks, unavailable model/evidence, failed extra checks,
unhealthy rejection despite passing checks, malformed input, cost-caused misses,
critical fallback, and accepted-history invariants.

## Commands executed

From `V:\Real time systems project`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# Baseline before edits: 30 passed in 12.66s.
.\.venv\Scripts\python.exe -m pytest -v
# Final suite: 64 passed in 41.96s.
.\.venv\Scripts\python.exe -m compileall -q src tests
# Passed.
git diff --check
# No whitespace errors.
.\.venv\Scripts\python.exe -m src.ml.validate_sensor_dataset
.\.venv\Scripts\python.exe -m src.ml.evaluate_sensor_model
.\.venv\Scripts\python.exe -m src.ml.compare_validation_policies
.\.venv\Scripts\python.exe -c "from pathlib import Path; from src.ml import evaluate_sensor_dataset as e; e.OUTPUT_DIR=Path('results/policy_evaluation'); e.main()"
```

The dataset analysis chart was redirected to a new results folder to preserve the
old report/chart. Streamlit tests ran outside the sandbox because its temporary
directory cleanup was denied inside the sandbox. An initial test-harness relative
path error was corrected before the final successful run.

## Dataset and model

Validation: 20,629 records, 31 columns, four runs, no missing values, no duplicate
message IDs, and no invalid MAC/deadline flags or deadline-flag disagreements.
Dataset-recorded misses: 586 (2.84%); these historical labels do not demonstrate
live acceptance or cryptographic verification.

Fresh in-memory refit: training runs 0, 2, 3 (15,428 records); holdout run 1
(5,201 records). Accuracy **0.990386**, balanced accuracy **0.899108**.

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| normal | 0.996060 | 0.995028 | 0.995544 | 4827 |
| anomalous_reading | 0.966777 | 0.989796 | 0.978151 | 294 |
| faulty | 0.730769 | 0.712500 | 0.721519 | 80 |

Confusion matrix, rows true / columns predicted in the same class order:

```text
4803    4   20
   2  291    1
  17    6   57
```

Full metrics, features and hashes: `results/policy_evaluation/sensor_model_evaluation.json`.
Existing model artifacts were not overwritten. The original artifact lacks split
provenance, so the evaluation refits a clone to establish the holdout. Four runs,
one holdout and unknown feature-generation provenance limit generalization claims.

## Illustrative policy comparison

Thirty identical synthetic input messages per mode, in five independent batches,
using real HMAC, replay monitoring, health model and scheduler. Each mode has the
same workload SHA-256 in `results/policy_evaluation/policy_comparison.json`.

| Mode | Accepted / 30 | Misses / scheduled | Deferred | Scheduled extra cost | Escalations | Accepted MAC/replay violations |
|---|---:|---:|---:|---:|---:|---:|
| Base EDF | 8 | 3 / 11 (27.27%) | 4 | 0 | 0 | 0 |
| Fixed validation | 5 | 6 / 11 (54.55%) | 4 | 22 | 15 | 0 |
| Risk adaptive | 7 | 4 / 11 (36.36%) | 4 | 10 | 10 | 0 |

All modes reject all five tampering, five replay and five out-of-range fault
messages. Accepted messages are from the normal scenario. The JSON also reports
outcomes by health prediction (not ground-truth class). Escalations count decisions
with positive extra validation cost. Costs count only scheduled tasks; checks run
before fallback, and rejection/deferred-check CPU demand is not modeled.

Adaptive validation falls between base and fixed costs/misses on this tiny fixture.
This is an illustration, not evidence of general performance or security superiority.
Base/fixed variants retain the same fail-closed health gates and exist only in the
offline experiment; the dashboard always uses the adaptive policy.

## Changes and remaining limitations

- Added/extended `risk_policy.py`, `additional_validation.py`, and
  `validation_config.py` for traceable assessment, responses, checks and parameters.
- Integrated them in `sensor_system.py`; added separate authentication/replay audit
  fields in `message_monitor.py` and malformed-envelope handling.
- Fixed missing-model fail-open health behavior and non-mutating feature reads.
- Added dashboard audit rendering and corrected its absolute-deadline label.
- Added backend/dashboard tests and reproducible evaluation/comparison scripts.
- Updated README and policy documentation; generated reports in the new results folder.
- Preserved datasets, saved models, the EDF scheduler, legacy login files, original
  tests, and environment. No Git commit or push was performed.

The legacy login model and MFA action regression passes. A separate pre-existing
issue was verified both in HEAD and the unchanged working files: importing
`src.security.security_system` fails because it imports `schedule_tasks`, which
does not exist in `src.scheduler.scheduler`. That obsolete wrapper is not part of
the sensor integration and has not been repaired in this change.

Other limits: demo keys, simulated time, no physical safe-state action, no live
latency measurement, and batch features based on previously accepted batches.

## Professor demonstration

```powershell
Set-Location 'V:\Real time systems project'
.\.venv\Scripts\python.exe -m pytest -v tests/test_policy_integration.py tests/test_dashboard_policy.py
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

Reset simulation state before each independent case. Submit valid LIDAR (default
values): moderate matrix risk, temporal/plausibility checks, extra cost 1, finish 5.
Reset and select CAMERA: low matrix risk, plausibility, cost 0. Reset and select
tampering or replay: security rejection, with no policy call for the rejected
message. Reset, select LIDAR and deadline 4: finish 5 and no acceptance. Expand
the backend audit to inspect the evidence and executed checks.
