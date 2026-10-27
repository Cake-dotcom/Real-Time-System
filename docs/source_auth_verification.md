# Source authentication verification — 2026-10-27

## Results

Final full suite: **99 passed in 16.88 seconds**, with no failed tests. This includes
the original 64 tests adapted to supply genuine sender sessions, 32 session/security
and benchmark tests, and three additional dashboard lifecycle cases. Existing
rejection/history assertions were retained; timing expectations now include the
explicit two-unit first-session charge. An intermediate full run passed 93 tests
before expiry-during-verification and extra dashboard tests were added.

The initial sandbox baseline run and an early regression run stalled at Streamlit
testing and were interrupted. The preceding project revision had 64 passing tests
recorded in `policy_verification.md`; no fresh pre-edit full pass is claimed here.
The final suite ran successfully outside the sandbox. No required command remains
blocked. Compileall and whitespace checks passed; no dependencies were installed.

## Measured authentication benchmark

Final command, after all authentication code changes:

```powershell
.\.venv\Scripts\python.exe -m src.ml.benchmark_source_auth --messages 1000 --repetitions 10
```

Python 3.12.6, Windows 11, `perf_counter_ns` elapsed timer. Ten paired repetitions
with alternating mode order; each has 1,000 valid, 50 replay and 50 tampered attempts,
three sources. Warmup excludes 30 valid messages per mode. All semantic inputs and
security gates are identical; fresh nonce/session material differs as required.

| Metric, aggregated over 10 repetitions | Full source authentication each message | Reuse |
|---|---:|---:|
| Full handshakes | 11000 | 30 |
| Successful reuses | 0 | 9970 |
| MAC verifications | 11000 | 11000 |
| Failed authentication events | 1000 | 1000 |
| Replay rejections | 500 | 500 |
| Accepted injected attacks | 0 | 0 |
| Exchange mean / median / p95, µs | 72.846 / 70.100 / 89.200 | 23.907 / 22.800 / 27.500 |
| Receiver mean / median / p95, µs | 41.268 / 39.600 / 49.200 | 13.417 / 12.800 / 13.900 |
| Receiver authentication total, ms | 453.9448 | 147.5821 |
| Loop elapsed total, ms | 811.8366 | 271.4673 |
| Process CPU total, ms | 796.875 | 281.250 |

Measured receiver reduction: **67.48898%**; exchange mean reduction: **67.18113%**.
These values describe the final local run; an earlier run before the final expiry
guard measured about 66%, illustrating host noise. No ECU/network or prior bare-HMAC
speedup is claimed. Process CPU timer quantization can make short aggregated CPU
totals differ from elapsed totals. The JSON records individual repetition means,
workload hash, methodology and all counters: `results/source_auth/benchmark.json`.

## Policy comparison

Command: `.\.venv\Scripts\python.exe -m src.ml.compare_validation_policies`.
Forty semantic messages, five independent batches, actual saved health model.
Identical source/MAC/replay/health gates and workload hash in all modes. Each batch
has normal, tampered, replay, out-of-range fault, missing-session and unknown-source
attempts. Security violations include acceptance without a valid source session,
with a failed MAC, or with a failed replay gate.

| Mode | Accepted | Scheduled | Misses | Deferred | Rejected excluding deferred | Baseline + handshake + validation = total overhead | Escalations | Security violations |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| Base EDF | 5 | 11 | 6 (54.55%) | 4 | 31 | 11 + 22 + 0 = 33 | 0 | 0 |
| Fixed validation | 3 | 10 | 7 (70.00%) | 5 | 32 | 10 + 20 + 20 = 50 | 15 | 0 |
| Risk adaptive | 4 | 11 | 7 (63.64%) | 4 | 32 | 11 + 22 + 10 = 43 | 10 | 0 |

Miss rates use scheduled tasks as denominator. Overhead counts scheduled tasks;
checks for rejected/deferred tasks are not represented as processor demand. Rejected
counts include deadline misses. All non-normal scenarios have zero acceptance.
By-scenario and by-predicted-health counts are in `results/source_auth/policy_comparison.json`.
This small fixture illustrates timing consequences; it does not demonstrate broad
security/performance superiority. The old pre-session comparison is retained in
`results/policy_evaluation/` and is not directly comparable without the new costs.

## Model and dataset

Executed:

```powershell
.\.venv\Scripts\python.exe -m src.ml.validate_sensor_dataset
.\.venv\Scripts\python.exe -m src.ml.evaluate_sensor_model --all-runs --output-dir results/source_auth
.\.venv\Scripts\python.exe -c "from pathlib import Path; from src.ml import evaluate_sensor_dataset as e; e.OUTPUT_DIR=Path('results/source_auth'); e.main()"
```

Dataset: 20,629 rows, 31 columns, four runs, no missing values or duplicate message
IDs; flag consistency checks passed. Historical deadline misses: 586 (2.84%).
Dataset task outcomes are not proof of live authentication acceptance.

Reconstructed holdout run 1: accuracy 0.990386, balanced accuracy 0.899108, faulty
F1 0.721519. Saved-model predictions agree exactly with the fresh in-memory refit
on that split; saved split provenance is absent, so this is a diagnostic.

| Held-out run | Training runs | Accuracy | Balanced accuracy | Faulty F1 |
|---|---|---:|---:|---:|
| 0 | 1,2,3 | 0.977477 | 0.719700 | 0.230216 |
| 1 | 0,2,3 | 0.990386 | 0.899108 | 0.721519 |
| 2 | 0,1,3 | 0.980680 | 0.724228 | 0.263566 |
| 3 | 0,1,2 | 0.976487 | 0.711284 | 0.312500 |

Full per-class precision/recall/F1/support and confusion matrices are in
`results/source_auth/sensor_model_evaluation.json`. The original holdout is the
strongest of the four for faulty detection. No saved model was overwritten.
Four runs and undocumented feature-generation provenance prevent strong
generalization conclusions; accuracy is not proof of security.

## Changed files in this increment

| File | Purpose |
|---|---|
| `src/security/source_sessions.py` | Challenge/proof, domain-separated session keys/MACs, lifecycle, bounded storage, locks, metrics, safe public audit |
| `src/security/message_monitor.py` | Mandatory active-session/MAC/replay verification, fail-closed errors, measured verification time, first-message cost |
| `src/security/sensor_system.py` | Source audit/counters, exactly-once handshake cost, session-aware command-line demonstration |
| `src/security/security_system.py` | Repair old login wrapper via the existing scheduler API |
| `src/dashboard/app.py` | Sender handshake/reuse, reauthentication/revocation controls, actual status/overhead tables, safe error display |
| `src/ml/benchmark_source_auth.py` | Repeated, paired measured benchmark with shared mandatory checks and attack expectations |
| `src/ml/compare_validation_policies.py` | Real sessions in every policy, unknown/missing-session scenarios, complete overhead/violation accounting |
| `src/ml/evaluate_sensor_model.py` | Saved-model diagnostic and optional four-fold evaluation, configurable report directory |
| `tests/session_helpers.py` | Real proof exchange for migrated original fixtures |
| `tests/test_source_sessions.py` | Lifecycle, isolation, tampering, expiry, concurrency, exception, cost and benchmark regressions |
| `tests/test_sensor_system.py`, `tests/test_policy_integration.py` | Session-aware fixtures and cost expectations, retain previous invariants; add operational legacy check |
| `tests/test_dashboard_policy.py` | Backend audit/counter assertions and reuse/expired/revoked UI tests |
| `README.md`, `docs/source_authentication.md`, this report | Protocol, threat model, limits, methodology, results and commands |
| `docs/risk_validation_policy.md`, `docs/policy_verification.md` | Cross-reference the new source gate and identify old results as historical |
| `results/source_auth/` | New benchmark, model, comparison and dataset-chart artifacts |

The existing policy matrix, sensor thresholds, scheduler algorithm, datasets,
model artifacts and dependency versions are preserved. Previously untracked policy
files remain untracked; no commit or push was made.

## Demonstration and remaining requirements

```powershell
Set-Location 'V:\Real time systems project'
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
.\.venv\Scripts\python.exe -m src.security.sensor_system
.\.venv\Scripts\python.exe -m src.security.security_system
```

The legacy command was executed successfully: brute_force risk, temporary block,
and its demonstration task finishing at 2 before deadline 6. Dashboard integration
was verified with AppTest, including exact displayed/backend audit equality and
expiry/revocation/reauthentication; no manual browser session was required.

The sensor command also completed successfully: three handshakes, four MAC checks,
one reuse, and `CRITICAL_DEADLINE_FAILURE` for its deliberately tight task set.
RADAR finished at 6 before deadline 8; LIDAR finished at 14 after deadline 10 and
was not accepted. Camera work was deferred under the existing fallback behavior.

In the dashboard, reset for a fresh simulation, submit default LIDAR sequence 1
(finish 7), then sequence 2 (finish 5). The full-handshake counter remains 1 and
reuse rises to 1. Revoke the session and try the next sequence: rejection. Explicitly
reauthenticate and retry: a new session with a fresh first-message charge. Source
compromise requires trusted key rotation; simulation reset does not undo it.

No proposal source file was available, so the supplied request and handoff formed
the requirements audit. Remaining research/deployment gaps are deliberate and
documented in `source_authentication.md`: hardware/network evaluation, calibration,
DoS/rate limiting, durable key/revocation storage, authenticated admin access,
physical safe-state actions, mutual authentication, transport/encryption/forward
secrecy, formal real-time analysis and any multi-phase/limited-preemption EDF.
The contribution is an evaluated integration, not a new cryptographic standard or
a demonstrated research novelty claim.
