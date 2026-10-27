# Integrated sensor risk and validation policy

The source-authentication extension is documented in [source_authentication.md](source_authentication.md).
The live receiver now requires an authenticated session before per-message HMAC/replay verification.
Its one-time handshake cost (2 simulated units) is added separately to the existing per-message
baseline and validation cost. Current comparison outputs are under `results/source_auth/`.
The policy matrix and validation thresholds below are unchanged.

## Official basis

**NIST SP 800-30 Rev. 1, Guide for Conducting Risk Assessments**, National Institute of Standards and Technology, September 2012: [official PDF](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-30r1.pdf).
Exact basis: section 3.2, Tasks 2-4 (likelihood), 2-5 (impact), 2-6 (risk, printed p. 35), and Appendix I, Table I-2 (printed p. I-1). The code reproduces the exemplary qualitative matrix.

**NIST SP 800-82 Rev. 3, Guide to Operational Technology (OT) Security**, NIST, September 2023: [official PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf). Sections 4.1.2 (pp. 51–53) and 4.1.3 (p. 53) supply physical-consequence and risk-response context.

These are guidance, not a ready-made sensor policy. The evidence mappings, response table, thresholds, and costs below are project choices. Neither source prescribes EDF or this ML/HMAC implementation. This is not NIST certification, a complete organizational assessment, or a hard-real-time guarantee. See `policy_research_note.md` for the design recorded before implementation.

## Assessment assumptions

The event is **consuming an unreliable authenticated sensor reading**. Faults, errors, or compromised sensors can cause it; health predictions do not identify attackers. Normal/anomalous_reading/faulty predictions map to low/high/very-high overall likelihood proxies. A deterministic health issue with a normal prediction raises likelihood to moderate. These qualitative proxies are uncalibrated assumptions, not probabilities or separate estimates of event initiation and conditional harm.

Criticality 1/2/3 maps to moderate/high/very-high impact. Camera is 1; lidar/radar are 3. Real assignments need a physical hazard analysis. Missing/unrecognized prediction, unavailable model, invalid criticality, or missing/non-finite evidence produces unavailable risk and no acceptance. Handled inference errors also fail closed.

## Matrix and response

NIST Table I-2 cells (rows likelihood, columns impact):

| Likelihood / Impact | Very low | Low | Moderate | High | Very high |
|---|---|---|---|---|---|
| Very low | Very low | Very low | Very low | Low | Low |
| Low | Very low | Low | Low | Low | Moderate |
| Moderate | Very low | Low | Moderate | Moderate | High |
| High | Very low | Low | Moderate | High | Very high |
| Very high | Very low | Low | Moderate | High | Very high |

Project-defined response choices:

| Matrix risk | Local level | Required checks | Extra cost |
|---|---|---|---:|
| Very low / Low | low / standard | plausibility | 0 |
| Moderate | medium / additional | temporal consistency + plausibility | 1 |
| High | high / enhanced | temporal consistency + plausibility + stability | 2 |
| Very high | critical / reject | none | 0 |
| Unknown | unavailable / defer consumption | none | 0 |

Normal lidar/radar select moderate risk and cost 1; normal camera selects low risk and cost 0. Unhealthy readings remain rejected at every level, even if diagnostic extra checks pass. A large lidar jump with a normal ML prediction selects high risk, executes enhanced checks, and remains rejected. An anomalous lidar prediction yields very-high risk and rejection. Defer consumption creates no retry queue or physical safe-state actuation.

## Actual integration

`src/dashboard/app.py` calls `sensor_system.process_messages`, which executes:

1. `MessageMonitor.verify`: key lookup, HMAC comparison, sequence/replay verification.
2. Reading type/range, metadata, age, and finite non-negative timing validation.
3. `SensorFeatureTracker.build_features` and `SensorHealthMonitor.check`.
4. `assess_sensor_risk`: evidence mapping, Table I-2, response selection.
5. `validate_additional_checks`: selected checks and per-check pass/reason.
6. Rejection for unavailable evidence, unhealthy readings, policy rejection or failed checks.
7. `schedule_message_tasks`: execution plus baseline overhead plus extra cost.
8. Acceptance only on a met deadline, then feature and health history commits.

`select_validation_policy` remains a compatibility helper for already-assessed local levels. The live path calls the evidence assessment first. The old `mandatory_sensor_checks` placeholder now fails: features cannot attest mandatory gates.

Authentication/replay failures exit before health, policy, checks or scheduling. No policy response can override them. Failed MACs cannot advance replay state. Authenticated sequences advance even when later checks reject, preventing reuse; accepted feature/health history is separate. Batch features use history accepted before the batch. Empty history uses original startup defaults, an explicit simulation assumption, not demonstrated stability.

## Parameters and timing

`src/security/validation_config.py` centralizes project-defined range 0–200, absolute change <=20, absolute z-score <=4, standard deviation 0–15 and identical streak 0–9. Threshold magnitudes are preserved; negative stability features now fail. Calibrate using independent runs, sensor-specific units, false-positive/false-negative analysis, and hazard review.

Costs 0/1/2 and arrival/execution/baseline overhead/absolute deadline use abstract simulation units. Extra cost is added exactly once to eligible tasks. Message age is a separate feature in milliseconds; backend default zero is a simulator placeholder. CPU work for rejected traffic and validation of deferred tasks is not modeled as processor demand. EDF and critical-only fallback remain unchanged. The dashboard deadline label now correctly says absolute deadline.

## Inspectability and verification

The dashboard displays actual backend authentication/replay results, health, source identifier, likelihood/impact/matrix risk, response, rationale, uncertainty, checks/results, costs and deadline status. It exposes no secret keys. Early gate failures have no policy decision.

`tests/test_policy_integration.py` covers real coordinator execution, permissive-policy bypass attempts, low/medium/high behavior, missing evidence, check failures, cost-caused misses, malformed inputs, fallback, and history invariants. `tests/test_dashboard_policy.py` submits valid/tampered/replay UI scenarios, spies on actual policy calls and compares displayed JSON against backend results. Existing tests remain intact; login model and MFA have regression coverage.

## Reproduce

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
.\.venv\Scripts\python.exe -m src.ml.validate_sensor_dataset
.\.venv\Scripts\python.exe -m src.ml.evaluate_sensor_model
.\.venv\Scripts\python.exe -m src.ml.compare_validation_policies
```

Evaluation clones/refits the saved pipeline configuration in memory using GroupShuffleSplit (seed 42, 25% runs held out), preserving existing model files. It reports per-class metrics and confusion matrix. Original artifact split provenance is absent; the new refit establishes the split for this evaluation. Four runs and uncertain feature-generation provenance limit conclusions.

Comparison runs identical signed synthetic inputs through the real backend/model for base EDF, fixed and adaptive validation. Base/fixed overrides are confined to the experiment and retain the same fail-closed health gates. Outputs in `results/policy_evaluation/` include input hashes, scheduled deadline-miss rate, deferrals, overhead, escalations, outcomes by scenario/predicted health and accepted security violations. Health predictions are not ground-truth classes. This small illustration cannot establish superior security or real-world performance. Dataset-recorded outcomes are not rerun cryptographic verification.
