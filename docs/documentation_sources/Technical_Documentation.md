# 1. Executive overview

The Security-Aware Real-Time Sensor Scheduling System studies how mandatory message checks, health evidence and configurable protection costs interact with deadlines. Real in-process authentication feeds a simulated single-processor scheduler. This is not an RTOS, physical safety controller or deployment certificate.

The interactive laboratory creates signed demonstration messages from configurable recurring tasks. Production gates determine eligibility, the scheduler chooses work, and actual event traces drive the dashboard. Synthetic scheduling experiments bypass message generation explicitly; they do not claim to execute cryptography. A separate retained login-risk demonstration has its own model and action policy.

## Delivered functionality
- Source sessions, HMAC-SHA256 integrity, replay rejection, expiry and revocation.
- Input/timing checks, vehicle RF and SKAB GRU health evidence, additional validation and accepted-only history.
- Periodic/sporadic/one-shot jobs, fixed preemption points, admission, protected reservations, overload recovery and safe-stop records.
- Eight laboratory scheduling modes, seeded comparisons, event playback and CSV/JSON exports.

## Evidence boundaries
The saved cleanup suite passed 278 tests in 57.09 seconds; this is historical execution evidence, not a new full-suite run during documentation. The saved 20-seed optimization study demonstrates overload gains, while an explicit unexpected-risk example demonstrates a critical regression. Neither proves universal superiority.

Configured security levels/costs are simulation assumptions. Actual MAC verification occurs before admission; its configured budget is separately charged to simulated execution. Measured Python nanoseconds are never silently converted to WCET.

Start with src/dashboard/laboratory.py, src/lab/simulation.py and src/security/sensor_system.py. This edition changes documentation only. The validation record distinguishes commands executed now, commands checked against source and prior successful execution, and expensive commands deliberately not rerun.

# 2. Problem definition and requirements

Authentication, validation, stronger protection and interruption costs can consume deadline slack. Admitting every job during overload may waste capacity and still miss critical work. Reducing mandatory protection to improve a percentage is not a valid solution.

| Requirement | Implemented response | Limit |
|---|---|---|
| Authentic source and intact payload | Session proof and per-message MAC | Demo secrets; trusted receiver |
| Replay exclusion | Increasing source-wide sequence | In-memory state and boot context |
| Healthy evidence | RF/GRU and deterministic gates | Domain-specific models |
| Deadline acceptance | Actual completion versus absolute deadline | Simulated processor time |
| Critical protection | Admission and remaining reservations | Released jobs; overload can fail |
| Explain overload | Defer/reject/fail and safe-state events | No physical actuation |
| Comparable evidence | Shared workloads, events and seeds | Later trusted histories may diverge |

The optimization order is constrained: preserve mandatory security first, prioritize feasible protected completion, then overall completion and efficiency. Bounded subset heuristics are not a global online optimality theorem.

Task validation enforces positive execution, constrained deadlines no greater than periods, unique template IDs, legal release models and nonnegative preemption caps. Laboratory limits bound templates, jobs, intervals and events before allocation. See src/lab/config.py and src/scheduler/model.py for authoritative validation.

Non-goals include production automotive deployment, encrypted transport, certified safety, public administration, universal anomaly accuracy and guarantees for arbitrary overload. Tests establish observed cases, not exhaustive verification. Primary evidence groups are test_source_sessions.py, test_policy_integration.py, test_ra_lp_edf.py, test_scheduler_optimization.py and test_laboratory.py.

# 3. Complete architecture

[WORKFLOW]

The entry point src/dashboard/app.py calls the laboratory panel. compare/run in src/lab/simulation.py validates input and constructs tasks/events. RALPEDF invokes SecurityRuntime.release for each released job; it calls process_messages with isolated context and prepare_only=True. Gate failures cannot become admitted work. Successful gates insert an atomic mandatory_validation phase.

The engine admits, dispatches and advances event time. On-time completion invokes SecurityRuntime.complete. Only a sequence newer than the last committed reading updates trusted history. finish joins gate audits with final scheduler outcomes. The UI renders these records without inventing intervals.

## Distinct paths and interfaces
- Authenticated laboratory: real checks plus simulated CPU, src/lab/security.py.
- Synthetic runner: Task/Phase/RiskEvent directly into run_algorithm; no MAC execution claim.
- Older live panel: process_messages supports legacy and RA-LP-EDF, not all eight laboratory names.
- Login demo: evaluate_login combines RiskEngine, choose_auth_action and a legacy task; no sensor sessions.

run(raw, algorithm=None) returns configuration, workload identity, trace, security, policy and mechanisms. RALPEDF.run returns jobs, events, timeline, reservations, risk_history, metrics and snapshots. Policy is immutable configuration; Job contains mutable state. Security eligibility and scheduler admission remain separate decisions.

# 4. Repository and interface guide

| Path | Responsibility and contract |
|---|---|
| src/dashboard/app.py | Streamlit entry and retained live/dataset panels |
| src/dashboard/laboratory.py | Workload editor, playback, Gantt, comparison and exports |
| src/dashboard/scheduling_panel.py | Synthetic scheduling experiment controls |
| src/lab/config.py | Raw editor schema/units -> validated templates and events |
| src/lab/security.py | Release/completion -> gate audit, validation budget and history |
| src/lab/simulation.py | Config + algorithm -> joined authenticated run |
| src/lab/evaluation.py | Seeded configs -> repeated trial statistics |
| src/scheduler/model.py | Task/Phase -> released jobs, chunks and legal transitions |
| src/scheduler/ra_lp_edf.py | Jobs + risks + callbacks -> event-driven serial trace |
| src/scheduler/optimization.py | Optional/pinned demand -> subset and continuation rules |
| src/scheduler/feasibility.py | Budgets/deadlines -> envelope; separate static MPS analysis |
| src/scheduler/reservations.py | Protected budgets -> deadline-indexed consumption ledger |
| src/scheduler/security_costs.py | Interval inputs -> canonical cost categories |
| src/scheduler/scheduling_metrics.py | Simulation -> ratios, costs, risk and latency |
| src/security/sensor_system.py | Signed packets + timing -> gate decisions/tasks |
| src/security/source_sessions.py | Source proof/messages -> session lifecycle and verification |
| src/security/risk_policy.py | Health/features -> ValidationDecision; cannot authenticate |
| src/security/gru_health.py | Signed SKAB context -> fail-closed health evidence |
| src/ml/skab_dataset.py | Pinned recordings -> validated arrays/windows/manifests |
| src/ml/gru_sensor_model.py | Artifact + ordered window -> CPU anomaly predictor |

sensor_features.py builds accepted-history features; sensor_health.py retains vehicle RF; additional_validation.py executes named checks; validation_config.py centralizes assumptions. Models and data are runtime/reproduction assets. Tests and saved results are evidence, not replacements for gate execution. Existing packaging audit scripts do not alter algorithms.

# 5. Environment setup and command contracts

Python 3.12.6 was used in saved verification. Pinned dependencies include torch 2.7.1, scikit-learn 1.9.1, Streamlit 1.65.0 and Altair 6.3.0; requirements.txt is authoritative. The prior CUDA wheel was 2.7.1+cu126. Saved GRU inference explicitly loads on CPU.

## Required setup from repository root
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
python -m streamlit run src/dashboard/app.py
```

POSIX activation is source .venv/bin/activate. If PowerShell activation is restricted, invoke the environment's Python directly with -m; no machine-wide execution-policy change is needed. Installation should complete, pip check should find no broken requirements, and Streamlit should print a localhost URL.

All five models and prepared data are included. GRU requires matching .pt/.json files; vehicle RF requires sensor_health_model.joblib. The dashboard loads the vehicle CSV; SKAB tests/evaluation require prepared arrays and manifests. Training/acquisition is optional when included assets are intact.

The .venv was removed during cleanup. This documentation task uses bundled authoring tools and dependency-free scheduler checks; it does not reinstall the full application or claim a fresh network installation. Commands are verified against source/CLI definitions and prior test records. See the command ledger for exact input/output and failure contracts.

No production credential environment-variable interface exists. Ignoring .env and Streamlit secrets does not provision keys. Training and some evaluation scripts write fixed paths: preserve a separate checkout before running them. Missing imports require the correct interpreter/dependencies, not bypassing health/security gates.

# 6. Dataset documentation

| Dataset | Local files and population | Provenance / role |
|---|---|---|
| Vehicle sensor-message CSV | data/raw/av_sensor_messages.csv; 20,629 rows, 31 columns | Project-supplied; public source unverified. Vehicle RF/dashboard |
| Login activity CSV | data/raw/login_activity.csv; 15,000 rows, 11 columns | Supplied CSV; public source/split unverified. Legacy login only |
| SKAB v0.9 | data/raw/skab/data; 35 semicolon CSVs | Public water-circulation experiments. GRU and same-domain RF |

Official SKAB: https://github.com/waico/SKAB . Pinned data: https://github.com/waico/SKAB/tree/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/data . Individual URLs/hashes are in data/skab/source_manifest.json. No private login rows are reproduced.

Vehicle fields cover identifiers, reading statistics, MAC flags, timing and outcomes. The model excludes identifiers/post-scheduling outcomes. Targets are normal, anomalous_reading and faulty. Only four run groups are present. Recorded MAC flags are dataset features, not live authentication execution.

Login features: failed_attempts_last_5min, login_attempts_last_1min, unique_accounts_targeted, time_since_last_login_seconds, unusual_login_time, new_ip_for_user, successful_login. Labels: normal, suspicious, brute_force. timestamp/user_id/source_ip are present but not those seven inference features. The validator refers to a friend's CSV; a public download/license is not established.

SKAB ordered features: Accelerometer1RMS, Accelerometer2RMS, Current, Pressure, Temperature, Thermocouple, Voltage, Volume Flow RateRMS. Units cover vibration g, A, bar, degrees C, V and litre/minute. Binary anomaly is the target; changepoint is excluded. The anomaly-free recording uses documented nominal labeling.

The loader validates schema, finite values and chronology, groups overlapping recordings, excludes ambiguous targets and fits mean/std only on training. Windows allow one/two-second steps without resampling. Saved split: training 25 files/20 components/33,623 windows; validation five/five/4,863; test five/five/5,153. Source rows total 46,806; windows are correlated. Water-process anomalies are not vehicle faults or authenticated attacks. Retain data/raw/skab/LICENSE and attribution.

# 7. Machine-learning pipeline

## Vehicle RF
train_sensor_model.py uses nine numeric features (criticality, sequence delta, age, reading, delta, z-score, rolling standard deviation, identical streak, MAC flag) and sensor_type/reading_unit. Median imputation/scaling and categorical most-frequent imputation/one-hot encoding feed 300 balanced trees, seed 42. GroupShuffleSplit holds out 25% of run groups, seed 42. This is not a many-run train/validation/test study.

The bundle stores model/features. SensorHealthMonitor.check adds range/change checks and predicts without committing history. Missing artifact/features returns unavailable evidence. Four-fold vehicle diagnostics remain in results/source_auth/sensor_model_evaluation.json; original artifact split provenance is incomplete.

## GRU and same-domain RF
train_gru_sensor_model.py evaluates hidden/window pairs (32,20), (64,20), (64,64). A one-layer causal GRU uses final-state dropout .2 and a two-logit head. AdamW: lr .001, weight decay .0001, batch 256, at most 30 epochs, patience 5, gradient clipping 1. Training supplies class weights; validation selects epoch and threshold before test evaluation.

The saved winner has hidden size 32, window 20 and threshold .84. Metadata records scaler, features, architecture, split provenance and weight hash. GRUPredictor validates them and loads CPU weights. GRUHealthMonitor requires signed SKAB context and 19 trusted preceding observations bound to source/session/recording. Rejected readings cannot build trusted history. GRU anomalous output is mapped to the sensor policy vocabulary, not a new faulty class.

| Saved held-out SKAB metric | GRU | RF_refit_SKAB |
|---|---:|---:|
| Accuracy | .8317 | .8413 |
| Macro-F1 | .8143 | .8248 |
| Anomaly recall | .7125 | .7256 |
| False negative rate | .2875 | .2744 |

Source: results/gru/test_evaluation.json and evaluation_report.md. These are preserved measurements. SKAB RF is a separate refit, not the vehicle artifact applied to incompatible features. Outer group diagnostics and earlier inner validation diagnostics have different interpretations. The legacy login bundle supports predict_proba, but its original trainer/split protocol is absent; do not invent a retraining command or accuracy claim.

# 8. Authentication and session lifecycle

Source: source_sessions.py, message_monitor.py, message_auth.py and test_source_sessions.py. The simple message_auth helper remains for legacy examples; the live receiver uses source sessions.

```text
Sender                         Receiver
Request challenge -----------> nonce + boot context
Proof with provisioned key ---> verify identity/challenge/expiry
Session established <--------- random ID and derived message key
Signed message ---------------> session check + per-message MAC
                               increasing source-wide sequence
Verification result <--------- public audit, not secret state
```

canonical_bytes uses sorted compact JSON, UTF-8, ensure_ascii and allow_nan=False. keyed_tag uses HMAC-SHA256 with protocol/purpose separation. Derived message keys bind challenge/session/source secret. The MAC covers the source/session/sequence and full payload. Verification uses constant-time comparison.

Challenge TTL is 5 seconds; session TTL 60 seconds, using monotonic time. Expired or revoked sessions reject. Replay counters survive reauthentication. A new receiver boot context invalidates old sessions. Revocation/rotation exist as explicit operations, not a durable production administration service.

Reuse saves only the handshake budget: 2 configured units on the first successfully verified message, zero thereafter. Every message still undergoes MAC/replay checks. Measured verification nanoseconds are separate. Laboratory costs are interpreted as milliseconds; legacy paths use their documented simulation units.

Unknown source, wrong MAC, invalid/replayed sequence or expired session fail before health/policy/scheduling. Passing a MAC does not imply healthy content. Replay state and accepted sensor history differ: a valid sequence may be consumed before later health/timing rejection; only final on-time acceptance commits trusted readings.

The receiver, clock, secrets and administrator are trusted. Demonstration keys are not production credentials. There is no encryption, forward secrecy, mutual receiver authentication, secure wire protocol or persistent revocation service. A stolen source secret permits impersonation until revocation/rotation. Do not expose private keys or full signed packets in public diagnostics.

# 9. Sensor-health validation and risk assessment

Configuration validation happens before simulation. Within process_messages, authentication/replay happens first, followed by reading/metadata/timing validation, accepted-history feature derivation, selected health inference and risk/additional-check decisions. This order must not be reversed in an architecture diagram.

## Project-defined bounds
- Reading: finite numeric, not bool, within 0-200. Missing sensor metadata fails.
- Message age and scheduling fields: finite/nonnegative. Default zero age is a simulator placeholder, not measured network latency.
- Temporal checks: absolute reading delta <=20 and absolute z-score <=4.
- Enhanced stability: standard deviation 0-15 and integer identical streak 0-9.
- Unknown check names fail. mandatory_sensor_checks cannot attest upstream gates and does not silently pass.

These are validation_config.py assumptions, not official NIST thresholds. Distance remains separate simulator evidence even for SKAB; it does not validate water-process physics.

## Distinct risk systems
The sensor gate maps normal/anomalous_reading/faulty to likelihood low/high/very_high. Normal with issues uses moderate. Criticality 1/2/3 maps to impact moderate/high/very_high. NIST Table I-2 combines them; very_low/low become local low, moderate becomes medium, high stays high and very_high becomes critical. Missing evidence becomes unknown. Unhealthy readings stay rejected even when additional checks pass.

The scheduler instead uses configured exposure*impact. Below .3 requests level 1; .3 to below .7 requests level 2; .7 or above requests level 3, subject to task/phase minima. Unknown, unconfident or stale evidence uses risk 1. Upgrades are immediate; downgrade requires dwell and threshold-minus-hysteresis. Policy defaults: dwell 5, hysteresis .05, TTL 100. Callers override these; laboratory defaults use their explicit unit conversions.

Source: security/risk_policy.py versus scheduler/dynamic_risk.py. Scheduler risk is explicitly configured exposure/events, not automatically a GRU probability or the NIST matrix result.

# 10. Security-policy engine

## Sensor validation policies
Every row supplements the same mandatory authentication/replay/input/health gates. More checks do not mean a different cryptographic authentication algorithm.

| validation_level | Trigger | Checks | Extra cost; response |
|---|---|---|---|
| standard | local low | reading_plausibility | 0; validate |
| additional | medium or helper sudden_change | temporal_consistency + reading_plausibility | 1; validate |
| enhanced | high | above + stability_check | 2; validate |
| reject | critical / confirmed_invalid | none | 0; reject |
| unavailable | unknown/missing/unrecognized | none | 0; defer, not admitted |

select_validation_policy creates ValidationDecision. The live caller uses assess_sensor_risk, executes required checks, independently rejects unhealthy evidence and requires a validate response with passing checks. unavailable becomes POLICY_UNAVAILABLE; it is not a promise of scheduler retry. See test_risk_policy.py, test_additional_validation.py and test_policy_integration.py.

Normal likelihood plus moderate impact yields low risk/standard checks. Normal likelihood plus very_high impact yields moderate matrix risk/additional checks. Critical risk rejects. High validation cannot rescue already-unhealthy evidence. Authentication failure never reaches the policy.

## Modeled scheduler protection
light/medium/strong are levels 1/2/3, effectiveness .25/.60/.90. They are cost/capability models, not executed replacement MACs. mandatory is a level-3 atomic phase representing the already executed gate budget. Risk narrows eligibility; timing failure never authorizes weaker protection.

## Separate login actions
RiskEngine score = 100*P(brute_force) + 70*P(suspicious) + 5*P(normal), rounded to two decimals. Boundaries: <30 low, <60 medium, <85 high, otherwise critical. These are provisional scores, not calibrated probabilities.

choose_auth_action returns password, password_plus_mfa, strong_mfa or throttle_and_strong_mfa respectively. Failed attempts >=10 override to temporary_block; unknown risk also blocks. These are action descriptors: no interactive MFA provider is implemented. Source: auth_policy.py, risk_engine.py, security_system.py. This policy is not used to establish sensor sessions. Each policy's meaning depends on its own inputs and executor, not on sharing the word risk.

# 11. Real-time scheduling foundations

A Task is a recurring template; a Job is one release. Absolute deadline d = release r + relative deadline D. Periods/deadlines must be positive with D<=period. Periodic releases r0+kT are strictly below the horizon; sporadic explicit arrivals respect minimum inter-arrival; one-shot has at most one release. Already released work drains after the horizon.

Phase.wcet is configured base execution, not hardware-measured WCET. A preemptible phase with quantum q has ceil(C/q) equal fixed chunks. A nonpreemptible phase is one chunk. Every chunk pays startup/teardown. Security fail-stop is different from a useful interruption that later resumes the same compliant work.

EDF orders eligible released work by absolute deadline, then textual criticality, release and ID. Protected means safety_critical or textual critical/high. Safety-critical can coexist with textual normal, so report both correctly.

## Code-aligned notation
- C: remaining configured base execution.
- Q_j: conservative full budget for released job j.
- B: unavoidable current blocking.
- t: simulation clock; d_j: absolute deadline.
- EDF prefix finish bound: t + B + sum(Q_j in prefix).
- Sufficient feasibility: each prefix finish <= its deadline.

A failed sufficient envelope does not prove no schedule exists. Static MPS analysis has different assumptions and does not certify dynamic risk or release-time gate costs.

## Illustrative example, executed for these documents
Two one-shot tasks release at 0: A base 2/deadline 3, B base 1/deadline 5. Each has one light interval in Optimized mode, with no interruptions or risk events. A finishes at 2.081; B at 3.142 simulation units. Additions include the .02 execution ratio, .02 startup, .02 teardown and .001 decision charge per interval. These deliberately chosen inputs are not benchmark measurements or physical cryptographic timings. Standalone scheduler inputs do not execute the real message gates.

# 12. Implemented scheduling policies

All eight laboratory modes share RALPEDF. Authenticated use shares the same production gate. Different names do not imply separate security implementations.

| Exact name | Main rule | Trade-off |
|---|---|---|
| Standard-EDF | Fixed level 1, checkpoint approximation; admission/reservations/overload off | Rejects higher mandatory requirements |
| Static-Sec-EDF | Fixed strong, checkpoint EDF | Higher modeled overhead |
| MPS-LP-EDF-structural | Strong, static fixed-point count construction when feasible | Narrow static assumptions |
| SAEDF-style | Prefer highest eligible level | Single-CPU inspired variant, not cluster reproduction |
| RA-LP-EDF | Original budgets, EDF, weighted objective | Conservative protected admission |
| RA-LP-EDF-Admission | Original selection with protected-first subsets | Bounded subset/search assumptions |
| RA-LP-EDF-Preemption | Continue when complete-current-first preserves all released bounds | Conservative interruption avoidance |
| RA-LP-EDF-Optimized | Subsets + continuation + least full-cost eligible interval | Unknown future risk can invalidate protection |

Original objective: alpha*risk*(1-effectiveness) + beta*overhead + gamma*switch_penalty; defaults 1/.15/.3. Dwell may retain a compliant feasible previous mechanism. Combined mode minimizes interval cost subject to eligible protection and feasible continuation. No weight authorizes an under-strength mechanism.

Policy also accepts internal modes outside the eight-choice registry: Highest-security fixes strong; Minimum-security minimizes total interval cost; No-switch-awareness suppresses the objective's switch penalty while physical switch costs remain. They are not synonymous with all flag ablations. No new dedicated benchmark result is claimed for each internal alias.

Legacy scheduler.py remains a separate nonpreemptive coordinator with ALL_SENSORS, CRITICAL_ONLY, CRITICAL_DEADLINE_FAILURE and NO_VALID_TASKS outcomes. The older live API accepts legacy or RA-LP-EDF only.

Inputs are tasks/events/policy/registry; outputs are auditable jobs, timeline and metrics. tests/test_ra_lp_edf.py covers the executor; test_scheduler_optimization.py covers variants and actual gates. Saved comparison.csv measures the principal strategies. Static baseline checkpoint transformations are documented rather than hidden as identical fixed-point structures.

# 13. Security-aware execution-cost model

At registry scale 1, security_costs.py defines:

| Mechanism | Level | Ratio | Startup | Teardown | Switch | Preempt/resume | Effectiveness |
|---|---:|---:|---:|---:|---:|---|---:|
| light | 1 | .02 | .02 | .02 | .02 | .02/.02 | .25 |
| medium | 2 | .08 | .05 | .05 | .05 | .02/.02 | .60 |
| strong | 3 | .16 | .10 | .10 | .10 | .02/.02 | .90 |

chunk_cost for base c contains c, c*ratio, startup, teardown, switch only when a non-null previous mechanism differs, resume only when needed, and decision_cost (default .001). Interruption is charged separately once to outgoing work. Registry scaling changes configured ratios/charges.

Original planning permits resume/switch/preemption at each remaining interval; protected reservations use maximum eligible costs, others minimum. Combined planning builds a compliant current-risk continuation with context allowances and projected dwell. Planning bounds are not actual consumed costs.

In the laboratory, actual gates run before admission. Prepared mandatory cost = per-message auth budget + selected validation 0/1/2 + first-session handshake 2. Default auth budget 1 plus normal critical-source additional validation gives 4 ms. This becomes an atomic mandatory_validation phase, not ordinary base demand multiplied a second time.

advance accounts for elapsed scheduler, switch, resume, preemption, startup, mandatory_validation, base, security_execution and teardown categories. Interrupted security work retains cleanup. Job totals and reservation debits conserve modeled CPU occupancy.

Session reuse avoids only handshake budget, never MAC/replay checks. Fixed intervals still pay setup/teardown; the model does not permit removing those charges. Budget caching saves Python calculation work, not security verification.

Measured wall-clock inference/MAC/runtime is separate from simulated costs. Rejected traffic consumes real computation but is absent from modeled CPU demand. Full-pipeline profiles include inference; scheduler-only profiles isolate decisions. Deployment needs measured complete resource budgets and OS/network interference, not a renamed simulation parameter.

# 14. Feasibility, admission and critical work

released_job_feasibility sorts released candidates by EDF and accumulates budgets from now+blocking. An infinite/invalid budget or first deadline violation returns failure with prefix evidence. RALPEDF.check treats current intervals and locked suffixes explicitly so demand is not paid twice or silently dropped.

## Original admission
Recheck active demand at events; shed noncritical, nonrunning work first when necessary. If protected assumptions still fail, record failure rather than claim success. New candidates are protected-first then EDF. Protected/unbounded failing candidates are rejected; normal jobs can defer. ReservationLedger stores deadline-indexed remaining budgets for admitted protected work, not a replenishing CBS server.

## Improved admission
Pin current atomic/capped work, select a protected subset, then fill spare capacity with normal work. At most eight optional jobs use descending-cardinality enumeration; ties retain admitted work, shorter demand and older releases. Larger sets use EDF insertion/largest-demand exchange. Exactness is conditional on that small optional population and fixed pinned set, not future arrivals.

Dropped normal work is retried at events. Reclaiming a ready suffix happens at a fixed point with one interruption charge and a resume flag. Protected bound failure produces an explicit reason and safe-state event. Failure of a sufficient test is not labeled inherent infeasibility without a lower-bound argument.

## Remaining failure modes
Critical jobs can exceed their individual deadline budget, arrive behind unavoidable blocking, face collectively excessive demand, lose evidence or encounter an unexpected risk increase. Advance reservations for unreleased critical jobs are not implemented. The safe-state record does not operate a physical actuator.

continue_without_preemption retains the previous job only if its entire remaining budget can finish first and all other released EDF bounds still fit. Each event/fixed point rechecks it. Feasible periodic progress is tested; universal starvation freedom under overload is not proved. The cache is cleared at decision epochs and keyed by cursor, mechanism, dwell/resume/cap state and override; cache-equivalence tests compare behavioral traces.

# 15. End-to-end worked examples

## Normal message - saved trace
results/laboratory/normal_operation.json records T1:0 with authentication/replay passed, mandatory budget 4 ms and completion 416.41 ms. Sequence: real gates -> RF health -> additional validation -> mandatory phase -> admission -> execution -> newer trusted history commit. This is saved simulation output, not physical latency or a new model benchmark.

## Tampered message
SecurityRuntime signs the payload, then changes distance_m for the tampered scenario. MAC verification fails with SECURITY_ALERT before feature/health policy and CPU admission. No trusted reading is committed. Original and optimized gate integration tests exercise this behavior.

## Replay or invalid sequence
The replay preset reuses an earlier completed signed packet. MAC can pass but source-wide sequence fails; the job is not admitted. Without an earlier accepted packet the lab reports SCENARIO_INVALID instead of manufacturing a replay. Reauthentication does not clear replay counters.

## Risk spike - saved counterexample
unexpected_spike_tradeoff.json has a critical one-shot job, base 1, deadline 5 and spike at .1. Original RA happens to choose strong and completes. Optimized chooses initially adequate light, then safely fails inside the interval. Both respect active protection. This is an explicit critical regression, not permission to continue under-strength.

## Feasible overhead - illustrative execution
With A base 2/deadline 3, B base 1/deadline 5, both released at 0 and one light interval each: A costs 2+.04+.02+.02+.001=2.081. B costs 1+.02+.02+.02+.001=1.061, so finishes at 3.142. The documentation validation executes this configured standalone example; authenticated laboratory work would also have a mandatory gate phase.

## Feasible subset - regression example
Three one-shot jobs share deadline 6: A base 4, B/C base 2, quantum 1. test_scheduler_optimization.py checks one original completion versus two for Admission. Selecting short feasible work can recover capacity. This is a correctness/example case, not a population study.

## Critical failure - preserved preset
Critical infeasibility yields zero of ten critical completions in both original and combined laboratory modes. Rejection/safe-state reasons remain in the trace. Rejected work is not counted on time; deadline-expiration ratios alone can hide it. Report critical_on_time_ratio and critical_noncompletion_ratio as well. The response is a software record, not braking/shutdown actuation.

# 16. Experiments and evaluation methodology

experiments.py uses seeded weights, periods 100/125/200, one to six phases, constrained deadlines and mixed periodic/sporadic arrivals. Base utilization excludes security. Scenarios are S1-low, S2-high, S3-gradual, S4-spike, S5-recovery, S6-multiple and S7-overload. S7 multiplies base demand by 1.5.

The saved optimization study preserves 800 pre-change runs and 800 final-stage runs. Final configurations: seeds 101-120, sizes 4/12, horizon 200, five scenario/load combinations, each repeated for original RA and three variants. Additional baselines come from the preserved baseline stage. Gzip JSONL holds exact tasks/events/traces; source archives identify versions. Original RA behavioral traces were reproduced exactly between stages.

| Scenario | Original total | Combined total | Original critical | Combined critical |
|---|---:|---:|---:|---:|
| S1-low U=.50 | 543/543 | 543/543 | 132/132 | 132/132 |
| S1-low U=.85 | 543/543 | 543/543 | 132/132 | 132/132 |
| S2-high U=.85 | 539/543 | 540/543 | 131/132 | 132/132 |
| S4-spike U=.85 | 534/543 | 534/543 | 123/132 | 123/132 |
| S7-overload U=.95*1.5 | 407/543 | 440/543 | 116/132 | 132/132 |

Source: results/optimization/comparison.csv. Overload completion rises 8.11% relative; critical completion 13.79%. Seed-paired mean completion-ratio gain is 5.75 percentage points, approximate normal 95% interval 4.03-7.47. Seed means average the two sizes, unlike pooled-count weighting. Saved high-risk decision latency worsened; do not select only favorable measures.

On-time ratios use all releases; deadline_miss_ratio counts deadline-expired states only. Noncompletion includes rejection/fail-stop. Separate admitted failures from never-admitted jobs. Cost categories expose startup, teardown, switching and interruption; residual risk is time-averaged configured exposure*impact*(1-effectiveness), not attack probability. Compliance is modeled executing time at required protection, not certification. Simulated utilization and Python wall time are different.

The separate 44 authenticated preset runs exercise real gates and show unchanged completion counts on those presets. Identical initial workloads can produce different later histories. Unit tests are not benchmark repetitions; a synthetic scheduler trace is not execution of cryptographic mechanisms.

# 17. Testing strategy and evidence

| Test group | Purpose |
|---|---|
| test_source_sessions.py | Proof/session lifecycle, expiry, revocation, tamper and replay |
| test_policy_integration.py | Bypass attempts, executed checks, deadlines and history |
| test_risk_policy.py; test_additional_validation.py | Matrix/profile outputs, missing evidence, named checks |
| test_sensor_system.py; test_adaptive_scheduling.py | Sensor and retained legacy coordination |
| test_skab_dataset.py | Provenance, schema, windows and split integrity |
| test_gru_model.py; test_gru_security.py | Artifacts, unsupported inputs and authenticated GRU path |
| test_ra_lp_edf.py | Fixed points, risk, cost/deadline/reservation invariants |
| test_scheduler_optimization.py | Subsets, caps, cache equivalence, gates and trade-off |
| test_laboratory.py | Recurring authenticated jobs, units, events and export |
| Dashboard test modules | Streamlit AppTest controls and backend correspondence |

```powershell
python -m pytest -q --tb=short
python -m pytest tests/test_scheduler_optimization.py -q
python -m pytest tests/test_source_sessions.py -q
```

Run from root in the installed application environment. Missing imports require correct dependencies; missing artifacts require restoring matching files. Never relax a mandatory security assertion simply to make a test pass. Seeded jobs/events/costs should reproduce; wall time may vary.

The latest saved full result is results/repository_cleanup/tests.log: 278 passed in 57.09s. It ran after cleanup in the temporarily relocated original environment, then that environment was removed. This edition does not claim another full suite without its dependencies. It performs dependency-free scheduling/policy checks, syntax/link checks, recorded-result validation and visual inspection of rendered documents.

Zero accepted replays in tests is not a cryptographic proof; a finite zero-miss sample is not an infinite-arrival timing guarantee. Retain adversarial and feasible-progress tests. Report critical regressions explicitly even when normal completion improves.

# 18. Dashboard and visualization

Start Streamlit on src/dashboard/app.py from root. Main laboratory tabs:

| Tab | Inputs and outputs |
|---|---|
| Simulation Setup | Presets/templates, units, horizon, seed, algorithms, backend and policy/cost controls |
| Live Simulation | Previous/next/final event, queue, clock, actual Gantt and per-job detail |
| Security and Sensor Monitoring | Gate/session/health records, risk and history counts |
| Results and Analysis | Outcomes, critical failures, denominators and downloads |
| Algorithm Comparison | Same-workload deltas, side-by-side schedules and repeated trials |

Templates can be added, duplicated or removed. task:index denotes a release. Periodic/explicit sporadic arrivals stop at the horizon and released work drains. Phase JSON must sum to configured execution; invalid schema/limits/timing reject before simulation.

Risk changes can persist or recover after duration. Other conditions apply to matching releases. Replay requires prior completion. Vehicle presets choose RF; GRU without signed SKAB features/trusted context correctly fails closed.

Bars show actual executed intervals including security/cleanup. Markers show releases, deadlines, preemptions, switches and safe states from events. Playback is discrete-event history, not hardware telemetry. Slack is a conservative remaining-budget view, not a future-arrival certificate.

Export workload JSON, complete run/comparison JSON and job/event/security CSVs. Internal laboratory units are milliseconds; editor inputs may be seconds. Older legacy units must not be silently equated. Comparisons share inputs but completion-dependent histories may diverge.

Older live-message/dataset panels remain, with a narrower scheduling API. This is a local demonstration with trusted administration, not a hardened multi-user web service. The presentation PNG describes the authenticated laboratory path; its caption explicitly excludes synthetic benchmark authentication and legacy login from that path.

# 19. Troubleshooting and development workflow

| Symptom | Cause / safe remedy |
|---|---|
| Missing import | Restore environment and pinned requirements; check interpreter |
| Dataset path error | Run from root; restore raw/prepared files and manifests |
| GRU unavailable | Restore matching .pt/.json, correct feature order/domain |
| GRU context not ready | Use trusted commissioning; respect session/run/chronology |
| MAC or replay failure | Diagnose signing/session/sequence; do not disable gate |
| Policy unavailable | Supply valid evidence; fail closed meanwhile |
| Critical misses | Inspect bound, blocking and risk events; report real failure |
| Existing evaluation report | Preserve evidence/use separate checkout; do not overwrite test truth |
| Dashboard startup error | Correct interpreter/path or choose a free local port |

## Future development, not performed in this task
A new scheduling policy needs an explicit Policy mode and applicable registry entry, a bounded decision rule, trace explanations and adversarial tests. Keep gate callbacks, fixed points and cost semantics. Preserve the reference and evaluate paired identical workloads.

A sensor policy change belongs in risk_policy.py/validation_config.py and additional_validation.py. Give every new check an auditable name; test missing evidence and unhealthy/replayed rejection. Do not place mandatory authentication behind a permissive policy decision.

A new dataset needs provenance, redistribution rights, schema checks, domain-appropriate features and leakage-controlled splits. Do not convert vehicle distance into SKAB channels. Update metadata and unsupported-domain tests. Training is not automatic approval to promote new runtime weights.

For experiments, select unused output directories or separate checkouts, freeze seeds/configurations and record source hashes. Inspect per-job events before summary percentages. Do not edit runtime behavior to make documentation examples pass. Editable documentation lives in docs/documentation_sources; rendering and validation evidence live separately in docs/documentation_validation. The command ledger identifies destructive-to-evidence outputs before a teammate runs them.

# 20. Security, scientific validity and limitations

Per-message MAC/replay, health evidence and mandatory protection are implemented, but demo keys, trusted administration and in-memory state limit deployment. There is no encrypted transport, durable production revocation, hardened secrets, independent secure clock or public administration authentication. MFA actions are descriptors, not delivered factors. Only load trusted joblib/pickle artifacts.

The engine simulates serial execution. Configured budgets/effectiveness are assumptions; desktop Python timing depends on hardware/concurrency. Rejected-message computation is real work but absent from simulated demand. No calibrated conversion closes that gap. Static MPS and current-demand envelopes have separate scopes; neither certifies arbitrary dynamic risk.

SKAB is one water rig with overlapping/ambiguous samples, not authenticated attacks or a faulty subclass. Vehicle data has four runs; public provenance of vehicle/login CSVs is unverified. GRU held-out macro-F1 is below comparable SKAB RF. Accepted-only live history can diverge from offline windows. Scores are not calibrated attack probabilities.

Optimized heuristics recover some overload capacity, but future releases/threats are unknown. Protected jobs can still fail; least-cost adequate protection can be less resilient to a later spike than initially stronger protection. Present saved gains and counterexamples together.

## Future work, explicitly unimplemented
Measure complete costs/rejection load on target hardware; validate transport and durable key lifecycle; collect independent domain-appropriate data; calibrate decision thresholds; explore advance critical reservations; integrate a validated physical safe-state controller; evaluate broader fairness and risk trade-offs. These are proposals, not hidden delivered features.

There is no root project license. Preserve SKAB attribution/license and review rights for supplied datasets before redistribution. These documents print no private source rows or secret values. Historical evidence and its original provenance metadata remain unchanged.

# 21. Glossary and references

| Term | Meaning here |
|---|---|
| EDF | Earliest absolute deadline among eligible work |
| RA-LP-EDF | Project risk-aware limited-preemption EDF engine/reference |
| Task / job | Recurring template / one release with absolute deadline |
| MAC | Keyed integrity/authenticity tag; not encryption |
| Replay | Reuse of an authenticated old message or sequence |
| Admission | Include security-eligible released work under a budget bound |
| Feasibility | Sufficient current envelope or separately scoped static test |
| Preemption | Interruption/resumption at a permitted point with costs |
| WCET | Worst-case execution time; configured budgets here are not certified |
| Anomaly detection | Domain-specific classification, not malicious attribution |
| Residual risk | Time-averaged configured exposure*impact*(1-effectiveness) |
| Safe state | Recorded failure response, no physical actuator |
| Dwell / hysteresis | Rules preventing premature downgrade |

## Primary sources, verified links
- SKAB official repository: https://github.com/waico/SKAB . Pinned original URLs/hashes: data/skab/source_manifest.json. Citation: Katser and Kozitsin, Skoltech Anomaly Benchmark (2020), https://doi.org/10.34740/KAGGLE/DSV/1693952 .
- NIST SP 800-30 Rev. 1, Guide for Conducting Risk Assessments: https://csrc.nist.gov/pubs/sp/800/30/r1/final . Project basis: section 3.2 Task 2-6; Appendix I Table I-2.
- NIST SP 800-82 Rev. 3, Guide to Operational Technology (OT) Security: https://csrc.nist.gov/pubs/sp/800/82/r3/final . Project context: sections 4.1.2-4.1.3.
- Limited-Preemption EDF Scheduling for Multi-Phase Secure Tasks: https://drops.dagstuhl.de/entities/document/10.4230/LITES.10.1.3 . Repository references sections 2, 3.2, 4.1-4.3 and corrected equation 9; dynamic extensions are not that theorem.
- Xie and Qin, Scheduling Security-Critical Real-Time Applications on Clusters: https://taoxie.sdsu.edu/publication/tc06.pdf . SAEDF-style here is only a single-CPU inspired comparison.
- PyTorch GRU API: https://docs.pytorch.org/docs/stable/generated/torch.nn.GRU.html . Installed version is pinned separately; stable docs can be newer.
- scikit-learn RandomForestClassifier: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html .

Other sensor-profile and optimized decisions are implementation choices, not claims of a newly proved published algorithm. Refer to the accompanying source/command ledger and recorded validation for this edition's reproducibility boundaries.
