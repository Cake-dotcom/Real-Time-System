# 1. Project at a glance

**Security-Aware Real-Time Sensor Scheduling System**

One sentence: authenticate sensor messages, assess health, account for protection costs, then schedule eligible work against deadlines and explain every outcome.

## The problem
- Security work consumes time; ignoring it can make a schedule look feasible when it is not.
- Critical work needs protection during overload, but criticality alone cannot make impossible deadlines feasible.
- Missing evidence, tampering and replay must never be traded for a better completion percentage.

## What to emphasize
- Real in-process session/MAC/replay and health gates feed a simulated scheduler.
- Fixed-point EDF, admission, reservations and risk adaptation are integrated with an auditable dashboard.
- Compare identical workloads and show failures as well as improvements.
- Contribution: an integrated, testable laboratory and measured policy comparisons; not a new universal scheduling theorem.

## Stack and scope
Python 3.12; Streamlit/Altair; pandas/NumPy; scikit-learn RF; PyTorch GRU; HMAC-SHA256; pytest. Versions are pinned in requirements.txt. The latest saved full suite is 278 passes; this documentation edition does not claim a new full-suite run.

**Say aloud:** “Security changes the cost of eligible work. That changes the deadline budget, so admission and execution must account for it.”

**Do not say:** certified hard real time, guaranteed critical deadlines, GRU proves vehicle safety, or simulated light/strong levels are replacement cryptographic protocols.

# 2. How it works

1. **Configure and release.** Editor validation creates templates and timed jobs. Source: src/lab/config.py, scheduler/model.py.
2. **Create signed input.** Laboratory sender creates the scenario packet. Source: src/lab/security.py, release.
3. **Authenticate and reject replay.** Source/session, full MAC and source-wide sequence checks run first. Source: security/source_sessions.py, message_monitor.py.
4. **Validate reading and timing.** Range, metadata and finite/nonnegative simulator fields. Source: security/sensor_system.py.
5. **Evaluate health.** RF vehicle features or GRU signed SKAB context; missing evidence fails closed. Source: sensor_health.py, gru_health.py.
6. **Assess sensor risk; execute checks.** Qualitative matrix selects standard/additional/enhanced/reject/unavailable. Source: risk_policy.py, additional_validation.py.
7. **Budget mandatory and modeled security.** Add gate budget; configured scheduler risk controls eligible protection. Source: lab/security.py, scheduler/dynamic_risk.py, security_costs.py.
8. **Admit eligible demand.** Check released deadlines/budgets; protect feasible critical subsets. Source: feasibility.py, optimization.py.
9. **Execute at fixed points.** Dispatch, account costs, recheck risk/deadlines, defer/reject or safe-stop. Source: ra_lp_edf.py.
10. **Commit and explain.** Only on-time newer readings update trusted history; all outcomes reach trace/UI. Source: lab/security.py, dashboard/laboratory.py.

**Order caveat:** workload configuration is validated first, but received-message MAC/replay precedes physical/timing checks. Synthetic scheduler-only experiments do not execute the real gates. Legacy login is separate.

# 3. Datasets, ML and policy names

## Distinct datasets
- **SKAB (Skoltech Anomaly Benchmark):** water-circulation recordings; eight physical channels; binary anomaly. Official: https://github.com/waico/SKAB . Pinned URLs/hashes: data/skab/source_manifest.json.
- **Vehicle CSV:** data/raw/av_sensor_messages.csv, 20,629 records, four runs. RF/dashboard; no verified public source URL.
- **Login CSV:** data/raw/login_activity.csv, 15,000 records. Separate legacy login-risk; no verified public source or split protocol. Do not call it SKAB.

## Models
- Vehicle RF: normal/anomalous_reading/faulty; 300 trees, grouped run holdout.
- GRU: SKAB normal/anomalous; saved hidden 32, window 20, threshold .84. Requires trusted prior context. Saved macro-F1 .8143 versus .8248 for the separately refitted SKAB RF. Not vehicle accuracy.
- Legacy login bundle: predicts login classes; original training provenance is incomplete.

## Principal scheduler names
Standard-EDF; Static-Sec-EDF; MPS-LP-EDF-structural; SAEDF-style; RA-LP-EDF; RA-LP-EDF-Admission; RA-LP-EDF-Preemption; RA-LP-EDF-Optimized. Original RA is the laboratory default. Admission changes subset choice; Preemption avoids safe-to-avoid interruptions; Optimized adds least-cost compliant selection. Legacy EDF is separate.

## Three policy vocabularies
- Sensor validation: **standard, additional, enhanced, reject, unavailable**. Extra configured cost 0/1/2 for low/medium/high. MAC/replay remains mandatory.
- Modeled mechanisms: **light, medium, strong**; levels 1/2/3, scheduler risk thresholds .3/.7 plus minima/dwell/hysteresis.
- Login action descriptors: **password, password_plus_mfa, strong_mfa, throttle_and_strong_mfa, temporary_block**. No implemented interactive MFA provider.

# 4. Examples to explain verbally

## Normal authenticated message
Situation: saved T1:0 normal preset. Decision: gates pass, budget 4 ms mandatory work, then schedule. Reason: healthy/validated and feasible. Outcome: NORMAL at 416.41 ms simulation time; newer history committed. Source: results/laboratory/normal_operation.json.

## Tampered payload
Situation: payload changes after signing. Decision: SECURITY_ALERT before admission. Reason: MAC no longer matches full content. Outcome: no CPU work or trusted reading commit.

## Replay
Situation: previously completed signed packet is reused. Decision: sequence/replay rejection even if MAC passes. Reason: authenticity does not imply freshness. Outcome: never admitted; without a prior packet the scenario is explicitly invalid.

## High scheduler risk
Situation: configured exposure*impact rises to at least .7. Decision: require level 3 subject to task/phase minima. Reason: current evidence requires stronger modeled protection. Outcome: upgrade at permitted dispatch; under-strength running atomic work safely stops. It is not a new real MAC algorithm.

## Overload
Situation: three jobs, same deadline 6, bases 4/2/2, quantum 1 (regression example). Decision: Admission can select two short jobs instead of one long job. Reason: feasible subset cardinality after protected demand. Outcome: two completions in that test; no universal optimality claim.

## Critical failure
Situation: preserved Critical infeasibility preset. Decision: reject/fail according to bounds. Reason: configured demand cannot be accommodated by the selected policy. Outcome: 0/10 critical completions in both original/combined saved runs, with safe-state records. No physical actuator is controlled.

# 5. Talking points and likely questions

## Evidence you can quote
- Saved 20-seed, two-size overload study: original 407/543 total and 116/132 critical; combined 440/543 total and 132/132 critical.
- These are identical synthetic workloads, not a guarantee for every workload. Authenticated preset completion counts remained unchanged.
- Explicit unexpected-spike example: original chooses strong and survives; optimized initially chooses sufficient light and must stop after the spike. Do not hide that critical regression.
- Latest saved full suite: 278 passed in 57.09s. Test cases and benchmark repetitions are different evidence.

## Three likely questions
**“Can you guarantee every critical deadline?”** No. The engine checks currently released budgets and fixed blocking. Future arrivals, risk changes or overload can invalidate feasibility; it records failures rather than inventing success.

**“Is the GRU better, and is it a vehicle model?”** It is a SKAB water-process model. Its saved held-out macro-F1 is lower than the same-domain RF, although its artifact is smaller. No vehicle generalization is established.

**“Does session reuse skip security?”** No. Only repeated handshake budget is avoided. Every message still needs session validity, MAC and replay verification, then health/policy and deadline acceptance.

## Demonstration sequence
Start dashboard -> Normal operation -> Run laboratory -> inspect actual Gantt/security audit -> Tampered and replayed -> compare original and optimized on one unchanged workload -> show a critical failure and explain why it is reported.

**Closing sentence:** “The contribution is making security eligibility, execution costs and deadline outcomes observable in one reproducible laboratory, with explicit limits.”

Sources: README.md; docs/scheduler_optimization.md; results/optimization/report.md; docs/gru_sensor_model.md. Official policy references: https://csrc.nist.gov/pubs/sp/800/30/r1/final and https://csrc.nist.gov/pubs/sp/800/82/r3/final .
