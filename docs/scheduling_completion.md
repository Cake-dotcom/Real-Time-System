# Scheduler implementation delivery — 2026-10-28

The working simulator and live adapter are implemented and tested. Hardware WCET,
infinite-horizon dynamic schedulability, calibrated security effectiveness and
faithful reproduction of every published baseline remain outside the evidence.
These limits are explicit rather than hidden behind a completed-function count.

## Verification

Baseline before this task: **148 passed in 37.15 s**. Final run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
# 200 passed in 48.06s; 0 failed, 0 skipped
```

The final suite includes existing login/MFA, authentication, tampering, replay,
source/session lifecycle, RF, GRU, missing artifacts, dataset and dashboard tests.
New tests exercise the real adapter in RF and GRU pipelines, check that attacks
never reach scheduling, and prohibit history commits after timing/health failure.
The new AppTest selects RA-LP-EDF on the live dashboard and runs the laboratory.
Twenty seeded scheduler tests check deadline, accounting, security and reservation
invariants. Hand cases cover exact cost totals, three phases, fixed-point startup,
actual preemption/resume, capped preemption, protected admission, mid-interval risk
spikes, mandatory upgrades overriding dwell, unknown risk, deferral/recovery,
overrun safe-stop, static subdivision and constant-risk drain-time freshness.

Windows sandbox attempts stalled in the full Streamlit/test run and experiment
run; those were interrupted. The completed full suite and full evaluation ran
with approved execution outside that sandbox. No tests were removed or weakened.
The original preemption test exposed a missing state transition; a new protected
arrival test exposed underestimated blocking after a preemption cap. Both were
fixed. Scenario evidence freshness was extended through the final job deadline
so low-risk scenarios do not accidentally become stale during drain time.

Evaluation command:

```powershell
.\.venv\Scripts\python.exe -u -m src.scheduler.experiments --full --workers 4
.\.venv\Scripts\python.exe scripts/report_scheduling.py
```

The grid contains **3,500 main runs**: 7 scenarios × 5 task counts × 4 utilizations
× 5 seeds × 5 algorithms. There are **110 sensitivity/ablation runs**. See
[actual results, variation and paired intervals](../results/scheduling/evaluation_report.md).
Sources and metadata are retained; runtime is a wall measurement under stated
worker concurrency. No performance gain is asserted without those observations.

## File inventory

| File | Responsibility |
|---|---|
| `src/scheduler/model.py` | Validated tasks, phases, release generation and job state transitions |
| `src/scheduler/security_costs.py` | Mechanism registry, provenance and canonical component budgets |
| `src/scheduler/dynamic_risk.py` | Independent exposure/impact, confidence, expiry, thresholds and dwell |
| `src/scheduler/feasibility.py` | Finite released-job envelope and separately scoped static MPS analysis |
| `src/scheduler/reservations.py` | Protected remaining-demand ledger and debit/violation accounting |
| `src/scheduler/ra_lp_edf.py` | Event engine, EDF dispatch, fixed points, admission, costs, safe-stop and overload |
| `src/scheduler/scheduling_metrics.py` | Explicit populations, denominators and wall/simulated time separation |
| `src/scheduler/sensor_adapter.py` | Verified one-shot messages to phases, preserving mandatory validation cost |
| `src/scheduler/experiments.py` | Paired workloads, baselines, scenarios, ablations, statistics and hashes |
| `src/security/sensor_system.py` | Optional algorithm routing after all existing security/health gates |
| `src/dashboard/app.py` | Live scheduler selection and real trace invocation |
| `src/dashboard/scheduling_panel.py` | Laboratory controls, timelines, risk, metrics, assumptions and saved comparisons |
| `tests/test_ra_lp_edf.py` | Unit, hand-derived, randomized and reproducibility checks |
| `tests/test_policy_integration.py`, `tests/test_gru_security.py` | Additional RF/GRU real-coordinator gate and history tests |
| `tests/test_scheduling_dashboard.py` | Actual Streamlit live-adapter/laboratory wiring |
| `scripts/report_scheduling.py` | Saved-result integrity checks, report and scientific plot |
| `docs/scheduling_design.md` | Algorithm, references, assumptions, metrics and reproduction commands |
| `docs/scheduling_traceability.md` | Audit and pre-implementation requirement map |
| `README.md`, this document | Entry points, delivered status and limitations |
| `results/scheduling/` | Raw runs, 700 workloads, aggregates, paired differences, sensitivity, metadata and 35 full traces |

Prior GRU-stage changes remain present. This stage did not retrain, replace or
remove the RF/GRU models, datasets, session implementation or legacy scheduler.

## Requirement traceability

“Completed” below is scoped to the documented simulation/prototype model. Partial
rows identify the missing subrequirements; none imply a deployment certificate.

| Master section | Status | Evidence and remaining scope |
|---|---|---|
| 1. Responsibility | Completed | Audit, implementation, full regression and actual saved evaluation delivered |
| 2. Research direction | Partially completed | Working research platform; deployment guarantees and externally validated superiority are not established |
| 3. Repository audit | Completed | `scheduling_traceability.md`, active import path and 148-test baseline; legacy/RF/GRU roles distinguished |
| 4. Mandatory security | Completed | Existing gates retained; RF/GRU adapter integration tests for MAC/replay/session/health/timing/history |
| 5. Task/job model | Completed | `model.py`; periodic/sporadic/one-shot release, constrained deadlines, criticality, phases, states and validation tests |
| 6. Multiple phases | Completed | Ordered phase plans and fixed chunks; three-phase exact-accounting and static subdivision tests |
| 7. WCET/cost accounting | Partially completed | Explicit simulated component costs, sensitivity factors and overrun safe-stop; no trustworthy measured hardware WCET data is available |
| 8. RA-LP-EDF | Completed | `ra_lp_edf.py`; release/risk/completion/deadline events, EDF, bounded mechanisms, constraints and logs; genuine preemption tests |
| 9. Limited preemption research | Partially completed | Official paper sections investigated; fixed points, blocking, caps and conservative static construction implemented; independent author-code equivalence remains pending |
| 10. Admission | Completed | Proposed + admitted demand checked with costs, critical bounds and blocking; explicit rejection/defer/recovery and cap-arrival tests; no infinite-release claim |
| 11. Reservations | Completed | `reservations.py`; released critical window = release/deadline, worst compliant remaining bounds, debit/release events; recurring server extension is future work |
| 12. Overload | Completed | Noncritical shedding, deferral/recovery, protected rejection and safe-state; overload experiments and hand cases |
| 13. Per-task risk | Partially completed | Exposure×impact with missing/stale/uncertain handling, scenario events and tests; live external threat calibration is unavailable, so production exposure is unknown |
| 14. Minimum protection | Completed | Task/phase minima, thresholds, hysteresis, immediate upgrades and no silent downgrade tests |
| 15. Mechanisms | Completed | Three explicit synthetic cost/capability/effectiveness profiles; mandatory real authentication kept upstream; these profiles do not execute new crypto |
| 16. Optimization | Partially completed | Hard filtering before bounded three-candidate objective, dwell and sensitivities; greedy local policy, no global lookahead optimum or solver comparison |
| 17. Risk changes | Completed | Fixed-point upgrades and immediate under-strength fail-stop/cleanup inside atomic regions; sudden spike and safe-state tests |
| 18. Schedulability | Partially completed | Conservative finite demand envelope plus separately scoped static test; no infinite-horizon dynamic proof or independent full formal verification |
| 19. Metrics | Partially completed | Timing, populations, costs, critical outcomes, risk, reservations, response percentiles, preemptions and wall times; no dedicated per-job blocking-duration aggregate or deployment latency bound |
| 20. Baselines | Partially completed | Five shared-workload algorithm variants measured; EDF is checkpoint-discretized, MPS structural, SAEDF single-CPU; faithful original cluster reproduction not claimed |
| 21. Workloads/scenarios | Completed | n=4/8/12/16/20, U=.2/.5/.75/.95, seven scenarios, mixed arrivals/deadlines, phases1–6; critical/cost/error/cap sensitivity |
| 22. Statistics/integrity | Completed | Five paired seeds, raw/config/hash artifacts, per-configuration mean/SD/normal CI, paired differences, 110 ablation/sensitivity runs; exploratory statistical power documented |
| 23. Pipeline integration | Completed | Dashboard -> coordinator -> verified-task adapter -> engine -> deadline-gated history; live RF/GRU gate tests |
| 24. Dashboard | Partially completed | Real output charts/tables, events, risk, reservations, baselines and key controls; not every simulator parameter is editable and this is not a continuous real-time controller |
| 25. Tests | Completed | 200 passed, including preserved regression and new unit/integration/AppTest/invariant cases; not an exhaustive proof |
| 26. Documentation | Completed | README, design/reference note, metric definitions, algorithm/assumptions, commands and reproducible report |
| 27. Deliverables | Completed | Inventory, statuses, design, assumptions, tests, measured results, limits and prioritized next steps linked here |
| 28. Design alternatives | Partially completed | Greedy enumeration vs strongest/cheapest, fixed-point vs frequent checkpoints and reservation ablations; exhaustive/solver optimum and hardware complexity bounds not evaluated |
| 29. Overall success | Partially completed | Tested prototype and reproducible evidence delivered; stronger formal and deployment claims remain limited by the explicit gaps above |

No required local test remains blocked. Hardware WCET and threat calibration are
unavailable data, not failures masked by synthetic measurements. Faithful baseline
reproduction, recurring server guarantees, per-job blocking aggregation, exhaustive
optimizer comparison and wider dashboard editing remain precisely identified work.

## Algorithm and guarantee review

[The design note](scheduling_design.md) gives the execution steps, cost formula,
reference sections, EDF tie policy, fixed-point blocking, optimization, admission,
reservation semantics, overload, fallback and separate formal assumptions.
The primary static source is Standaert et al., DOI 10.4230/LITES.10.1.3, Sections
2, 3.2, 4.1–4.3 and corrected Equation (9). The live risk thresholds and objective
weights are project parameters, not attributed to NIST or to that paper.

Priority follow-up: (1) deployment WCET/safe-stop evidence, (2) recurring critical
servers and bounded-risk timing proof, (3) author-reference baseline validation,
(4) independent risk/effectiveness calibration, (5) more seeds, interactions and
measured optimizer/runtime comparisons. The current system should be presented
as a security-preserving research simulator with conditional timing bounds.
