# Interactive security-aware scheduling laboratory

The main dashboard now opens with a five-tab laboratory. It runs the existing
RA-LP-EDF engine and existing sensor-security gates against a complete editable
workload. The earlier single-message dashboard, GRU/RF controls, source-session
demonstrations and scheduler benchmark panel remain below it.

## Launch and first demonstration

From the repository root, using the existing environment and requirements:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

1. Open **Simulation Setup**. The default 15-second workload already contains
   LiDAR, radar, camera and a simulated IMU, with different release times, execution
   budgets, relative deadlines, periods and criticalities.
2. Leave **Health backend = RF** for these vehicle-feature demonstrations. Select
   **Tampered and replayed**, then **Load preset**, to add an invalid-MAC radar
   stream and a replay of the camera's earlier completed message at 3.2 seconds.
3. Add an event targeting `T1`, type `risk_spike`, time `0.02`, value `1`, duration
   `0`, repeat interval `0`, job number `0` to also demonstrate a mid-interval
   emergency fail-stop. Every event's other defaults are editable.
4. Select **Validate workload**, then **Run laboratory**. The workload is run as
   one competing CPU population, never as separately scheduled task traces.
5. Inspect **Live Simulation**: move the decision slider, step events, or jump to
   the final state. Select a job for its complete security, phase and cost audit.
6. Use **Security and Sensor Monitoring** to distinguish source authentication,
   MAC, replay, health, policy checks, scheduler eligibility and history commits.
7. Use **Results and Analysis** to inspect actual misses/rejections and download
   the complete JSON, jobs CSV, events CSV and security-audit CSV.
8. To compare the same configuration, choose **Compare algorithms** in Setup and
   run again. **Algorithm Comparison** provides absolute metrics and deltas from
   the chosen reference, plus downloadable traces for every algorithm.

The optional vehicle animation is not implemented. Manual trace playback and an
interactive Gantt chart are provided; playback does not execute or complete jobs.

## Designer semantics

All scheduler values are **milliseconds internally**. User-facing setup and chart
axes can use seconds or milliseconds. Switching the input unit converts existing
task, event, horizon, dwell, freshness and checkpoint values to preserve physical
durations. Weights, exposure, minimum security and job numbers are dimensionless.
Authentication cost and the explicitly labelled decision cost remain milliseconds.
Detailed backend audit tables and exported traces use milliseconds.

Each row is a task template. `T1:0`, `T1:1`, etc. are stable zero-based job IDs.
The event editor's `job_number` is explicitly **one-based**, with zero selecting
timestamp triggering. One-shot tasks release once. Periodic templates release at
offset plus successive periods. Sporadic templates use an explicit JSON arrival
list and enforce the minimum inter-arrival period. Releases exactly at the horizon
are excluded. Released jobs drain through completion, rejection or deadline
expiration; the observation interval is max(horizon, final drain time). Idle time
through the end of the horizon is shown in the laboratory trace.

Absolute deadline = release + relative deadline. The scheduler never stretches
the user's deadline or execution budget. Relative deadlines must be positive and
no larger than the configured period. A one-shot row may omit its unused period
or set it to zero, in which case its internal period equals its relative deadline.
Task/sensor IDs, enums, finite values, protection levels, phase sums and event
targets are validated. Shared sensor IDs must have consistent type/criticality.

The table supports adding and deleting rows; **Add task with defaults** and
**Duplicate task** provide useful starting points. Optional phase JSON uses the
selected input unit:

```json
[
  {"phase_id": "filter", "execution": 0.1, "quantum": 0.05, "minimum_level": 1},
  {"phase_id": "fusion", "execution": 0.15, "preemptible": false,
   "mechanisms": ["medium", "strong"], "minimum_level": 2}
]
```

These phases require a task execution budget of 0.25 in seconds mode. The default
phase is `application`. A mandatory authentication/validation accounting phase is
inserted **only after the real gates pass**; it does not overwrite the application
budget. Task quantum, phase preemptibility and maximum preemptions are respected.

Interactive guardrails: up to 32 templates, 200 releases per template, 500 jobs,
20,000 configured/baseline intervals, 1,000 expanded events and a one-hour release
horizon. Excessively small periods and quanta are rejected before allocating large
job/interval arrays. These are UI resource limits, not real-time guarantees.

## Security events

Target a task ID or sensor ID. Events at a release timestamp are processed before
that release's gates; completed intervals and history commits happen first at the
same timestamp. Multiple events retain configured order when timestamps match.

For message/health conditions, duration zero affects the next matching release;
a positive duration affects releases in the half-open interval [time, time+duration).
`repeat_every > 0` expands occurrences before the release horizon. A nonzero job
number instead attaches the event to that task's particular release. Risk events
persist; an optional duration returns exposure to that template's initial value.
Overlapping risk events use chronological assignment, not a nested threat stack.

| Condition/event | Actual behavior |
|---|---|
| valid | Real source challenge-response, signed payload, MAC/replay, health and policy checks |
| tampered | Change the payload after signing; the existing MAC verifier fails |
| replay | Reuse a signed packet from an earlier completed accepted reading of the same sensor |
| malformed | Sign a payload missing its reading; source/MAC may pass, basic validation rejects |
| faulty | Authentically sign an implausible reading; the production range gate rejects |
| anomalous | Explicit simulated health-evidence injection, labelled alongside the real model observation; not presented as a measured model prediction |
| unavailable | Explicit unavailable-health evidence; policy fails closed |
| risk_spike / risk_recovery | Feed the existing exposure/impact and minimum-level policy; dwell never delays upgrades |
| risk_unavailable | Unknown exposure requires conservative protection |
| revoke_session / expire_session | Modify the run-local receiver session lifecycle; subsequent real source verification fails |
| reauthenticate | Execute the existing source challenge-response again; source-wide replay counters persist |

A replay with no earlier completed accepted reading is a **SCENARIO_INVALID**
rejection. No prior acceptance is invented to manufacture a replay-detection count.
Sensor-targeted events can affect several templates sharing that source.

Each run creates fresh receiver state, keys, sessions, feature history and health
history. Session expiry uses simulated time converted to seconds, not playback
speed or Python wall time. Credentials, raw signed packets, keys and session IDs
are not exported. Random cryptographic nonces remain secure randomness; they are
not derived from a research seed. Nonsecret scheduling outcomes are reproducible;
measured wall durations naturally vary.

The laboratory uses `sensor_system.process_messages(..., context=..., prepare_only=True)`
to execute the **same production gate ordering**. Preparation leaves `accepted=False`
and does not schedule or commit. The scheduler's release hook rejects failed gates
before ready/admission/CPU execution. Its completion hook commits only previously
verified, on-time completed messages. An older job finishing after a newer accepted
reading cannot roll history back: its completion is recorded, but its reading is
not added to trusted history. Simultaneous jobs still compete in the one existing
event-driven scheduler.

Normal vehicle scenarios use the actual retained RF model, with one inference
worker on a run-local model copy. This avoids per-message thread-pool overhead and
a scikit-learn warning-filter race observed during the initial evaluation; weights
and artifacts are unchanged. Fault injection never turns unavailable evidence
into a normal prediction. GRU remains selectable and its original pipeline remains
intact, but the distance-only laboratory editor does not synthesize SKAB channels
or trusted commissioning history. GRU correctly rejects those vehicle inputs.
Generic/IMU labels use synthetic distance-based vehicle features, not validated
IMU-domain health models.

## Presets and qualitative expectations

Every preset is produced by `src/lab/config.py:preset`; there are no hard-coded
performance results in the UI.

| Preset | Configuration and intended observation |
|---|---|
| Normal operation | Four periodic sensors, offsets 0/.1/.2/.3 s; budgets .25/.15/.35/.10 s; deadlines 1/.8/1.5/1 s; periods 2/2.5/3/1.5 s |
| Simultaneous arrivals | Same templates, all offsets zero; demonstrates actual EDF contention |
| Critical pressure | One .3 s critical task versus three .7 s noncritical tasks, 1 s deadlines, 1.5 s periods; protected work remains feasible while lower-criticality work is deferred |
| Critical infeasibility | The critical budget becomes 1.2 s with a .6 s deadline; explicit rejection/safe-state rather than a manufactured guarantee |
| Tampered and replayed | Radar payloads tampered; camera replay at 3.2 s after its first completion |
| Sensor fault | Authentic radar reading outside the permitted range |
| Risk escalation | T1 exposure rises to 1 at .02 s inside its execution interval; emergency fail-stop may occur |
| Risk recovery | T1 starts at exposure .9 and drops to .1 at .1 s; the .5 s dwell prevents immediate downgrade |
| Overload | Four .7 s workloads, 1 s deadlines, 1.5 s periods; critical infeasibility and noncritical expiry remain visible |
| Periodic sensors | The normal recurring sensor templates, with independent job-by-job outcomes |
| Security versus performance | The risk-escalation workload shared across algorithms; strongest static protection can outperform RA-LP-EDF on completion |

Risk and security are separate evidence domains: the existing NIST-inspired sensor
validation policy selects and executes additional checks; the scheduler's exposure
events independently establish its required modeled mechanism. Risk probabilities,
effectiveness constants and synthetic cost profiles are not calibrated security
guarantees. See [scheduler design and references](scheduling_design.md).

## Playback, decisions and metrics

The clock slider selects a snapshot captured after a real scheduler decision.
Ready jobs are ordered by the same EDF deadline/tie fields; running capped jobs
may remain locked. Snapshots retain remaining bounds, base work, slack, required
level and safe-state count. A partially executed current interval may make its
displayed remaining bound conservative. Per-job final details explicitly include
future events relative to the playback cursor, so they are not confused with the
current state. No animation creates completion events.

Gantt bars use actual CPU intervals. Release triangles, deadline ticks and markers
for preemption, mechanism switches, misses and safe states come from backend data.
Idle intervals are explicit. Mechanism dispatch records include actual evaluated
candidates, objective values, timing verdicts and the dwell/selection rule.
Preemption-resume state survives deferral, so resume cost cannot disappear when
a preempted job is later recovered.

All released messages/jobs remain in the denominator, including security failures.
Admission rejections are counted separately from pre-scheduler gate rejections.
Executed means a start time exists; admitted means admission succeeded at least
once; completed means all phases finished on time. Deadline misses count actual
deadline expirations, not every rejection. Critical misses divide by critical
releases. Released on-time ratio is completed/releases; admitted on-time ratio is
completed/ever-admitted. Undefined ratios display N/A/null. Failed critical jobs
and their reasons have a dedicated table.

CPU utilization is all consumed modeled components divided by the observation
interval, including the idle tail and final drain. Security overhead excludes
application base and scheduler decision charges, and includes mandatory validation.
Residual risk averages risk×(1−assumed effectiveness) over modeled execution;
compliance is the fraction meeting the active policy. Both are conditioned on
execution and must be read alongside rejections/completion. They are not real
attack probabilities. See `scheduling_metrics.py` for the shared formulas.

Measured Python wall time includes run initialization, actual security/model
execution and simulation. The engine's wall metric includes callbacks and snapshot
capture; `scheduler_wall_ms` measures admission/dispatch work. Actual verification
nanoseconds and health-evaluation milliseconds are separate audit fields. Configured
cost units are never relabelled measured WCET. Rejected-message processing consumes
real Python time but is not charged to the simulated CPU model.

## Comparison, statistics and exports

Every algorithm receives the same templates, releases, event schedule and seed;
the exported `workload_id` verifies this. Each gets fresh security state. Different
completion decisions can change later trusted-history evidence and replay
availability; this is an explicit integrated-pipeline effect, not silently changed
input workloads. Template-only MPS analysis is marked **not an integrated trace
certificate**, because release-time validation costs are outside that analysis.

Standard EDF is fixed-light with the configured checkpoint approximation; it
still refuses under-strength execution. Static-Sec-EDF uses fixed strong protection.
MPS is a structural approximation and SAEDF is the existing single-CPU adaptation.
The minimum mandatory authentication phase is retained under every algorithm.
Do not infer faithful published-baseline superiority from these comparisons.

The comparison tab also offers **Repeated authenticated trials**. This reuses the
existing seeded workload generator, varying task count, base utilization and risk
scenario, then routes every release through the real gates. It generates new
workloads explicitly; changing only the seed of a fully specified editor workload
does not create independent samples. Means, sample SD, approximate normal 95% CIs
and paired differences are saved. Small repeat counts are exploratory, and normal
intervals can extend beyond ratio bounds. Large pure-scheduler grids remain in
the earlier experiment runner.

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -u scripts/evaluate_laboratory.py
.\.venv\Scripts\python.exe -u -m src.scheduler.experiments --full --workers 4
```

`results/laboratory/` contains all 11 actual preset traces, per-job/event CSVs, a
five-algorithm comparison, nine paired seeded trials, statistics and a generated
[demonstration report](../results/laboratory/report.md). JSON exports preserve
configuration, policy, mechanism provenance, source hashes, snapshots and security
audits. CSV cells containing structured values use JSON strings.

## Architecture and changed files

| Module | Change |
|---|---|
| `src/lab/config.py` | Validated task/event boundary, time conversion, resource bounds, 11 presets |
| `src/lab/security.py` | Isolated production-gate context, real signatures/replays, explicit health fault injection, completion-only commits |
| `src/lab/simulation.py` | Shared-engine orchestration, monitoring, comparison identity, CSV/JSON and playback access |
| `src/lab/evaluation.py` | Seeded authenticated sweeps and paired statistics using the existing generator |
| `src/dashboard/laboratory.py` | Five tabs, editable tables, validation/run/reset/export, actual trace charts and trial controls |
| `src/dashboard/app.py` | Laboratory entry above retained existing dashboard functionality |
| `src/security/sensor_system.py` | Optional run-local dependencies and preparation-only gate result; default behavior preserved |
| `src/scheduler/ra_lp_edf.py` | Release/completion/event hooks, snapshots, selection rationale, idle tail, corrected remaining accounting |
| `src/scheduler/model.py` | Persistent resume-needed flag across deferral/recovery |
| `src/scheduler/experiments.py` | Existing algorithm runner accepts registry/checkpoint and engine hooks |
| `tests/test_laboratory.py`, `tests/test_laboratory_dashboard.py` | Configuration, security, scheduling, exports, reproducibility and real Streamlit tests |
| `tests/test_ra_lp_edf.py` | Resume-cost regression after deferral |
| `scripts/evaluate_laboratory.py` | Reproducible preset/comparison/trial artifacts and report |

No second scheduling algorithm framework or duplicate authentication protocol was
introduced. The original global dashboard receiver remains available; the
laboratory never mutates it. Reset discards laboratory configurations/results and
the next run creates fresh security state.

Remaining limits: no hardware WCET or actuator safe-state integration; finite
released-job checks do not certify arbitrary future arrivals/risk changes; synthetic
health evidence is labelled; GRU commissioning and SKAB-channel editing are not
provided in this vehicle-oriented editor; automatic vehicle animation is omitted.
All major scheduling decisions can be traced to actual engine events rather than
an illustrative animation or prefilled metric.
