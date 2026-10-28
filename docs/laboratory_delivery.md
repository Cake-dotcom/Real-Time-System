# Interactive laboratory delivery

## Verification and measured evidence

The existing suite passed **200 tests in 39.15 seconds** before the upgrade.
The final complete suite passed **235 tests in 188.50 seconds**, with **zero
failures, zero skips and no warnings**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
```

The final suite ran alongside demonstration evaluation, so its elapsed time is
not an isolated performance benchmark. Regression coverage retains authentication,
tampering, replay, expired/revoked sessions, source lifecycle, RF, GRU, unavailable
models, trusted-history integrity, datasets, policy checks and legacy dashboards.

New checks cover editor validation and allocation limits, simultaneous/periodic/
sporadic releases, horizon boundaries, relative deadlines, unit equivalence,
authenticated failure scenarios, genuine replay after completion, fail-stop,
recovery dwell, protected overload, empty metrics, no overlapping CPU intervals,
cost conservation, deterministic comparison identities, run isolation, actual
Streamlit run/playback/reset/unit/preset/duplicate/compare behavior, and the
preemption-resume cost regression. Tests were not removed or weakened.

The demonstration runner completed **25 authenticated runs**:

- 11 presets, with full JSON and per-job/event CSV exports.
- The same risk-escalation workload under all five supported algorithms.
- Nine seeded trials: 3 distinct seeds × 3 algorithms, with means, sample SD,
  approximate normal 95% intervals and paired differences.

```powershell
.\.venv\Scripts\python.exe -u scripts/evaluate_laboratory.py
```

An independent pass over all 25 saved runs verified source hashes, successful
gates before CPU execution, history commits only for completed jobs, single-CPU
non-overlap, completion deadlines, cost conservation, zero reservation violations
and policy-relative execution compliance. The vehicle RF artifact and original
vehicle dataset hashes still match the pre-upgrade values.

The earlier pure-scheduler benchmark was also refreshed against the updated
engine: **3,500 main runs and 110 sensitivity/ablation runs**. Its report generator
validated the saved source hashes, paired configurations, representative trace
accounting and reservation/compliance counters before rewriting
`results/scheduling/evaluation_report.md`. These 3,610 simulator runs are separate
from the 25 authenticated laboratory runs above.

The initial evaluation exposed a scikit-learn thread-pool warning flood during
repeated single-reading predictions. Final laboratory inference uses one worker
on each run-local RF model; no weights or artifact files changed. All demonstration
results were regenerated with that final implementation. Initial failed tests
also exposed a mistaken assumption that a risk spike occurred during execution;
the actual EDF trace showed the job waiting. The preset now places its fail-stop
spike inside a known execution interval. Recovery and pressure presets separately
demonstrate dwell and feasible protected capacity.

## Actual examples

| Preset | Releases | Completed | Rejected by security gates | Admission rejected | Deadline expired | Safe-state events |
|---|---:|---:|---:|---:|---:|---:|
| Normal operation | 29 | 29 | 0 | 0 | 0 | 0 |
| Tampered and replayed | 29 | 22 | 7 | 0 | 0 | 6 |
| Sensor fault | 29 | 23 | 6 | 0 | 0 | 6 |
| Critical pressure | 40 | 10 | 0 | 0 | 30 | 0 |
| Critical infeasibility | 40 | 10 | 0 | 10 | 20 | 10 |
| Risk escalation | 29 | 28 | 0 | 0 | 0 | 1 |

In the pressure preset the ten completed jobs are the ten critical releases;
noncritical work expires. The infeasible variant explicitly rejects critical work.
An immediate security rejection is not misreported as a CPU deadline miss.

In the same-workload security-versus-performance comparison, RA-LP-EDF completes
28/29 jobs with 415.380 ms of configured security overhead. Static-Sec-EDF completes
29/29 with 980.780 ms. This demonstrates an actual trade-off: RA-LP-EDF does not win
every metric and can fail-stop a critical job during a sudden risk escalation.
These are synthetic cost-model observations, not cryptographic benchmarks.

See [the generated report](../results/laboratory/report.md) for every preset,
five-algorithm comparison and repeated-trial statistics. Raw traces and source
hashes are adjacent to that report.

## Definition-of-done evidence

| Requested capability | Delivered evidence |
|---|---|
| 1. At least four configurable tasks | Default four-row editor; add/duplicate/delete; validation and AppTest |
| 2. Valid/tampered/replayed/faulty messages | Real protocol and range gates; actual packet mutation and accepted-message replay; failure tests |
| 3. Timed risk events | Event editor, duration/repetition/job triggers, existing RiskEvent policy; escalation/recovery tests |
| 4. Chosen horizon | Seconds/ms input boundary, excluded horizon releases, explicit drain/idle tail |
| 5. Recurring jobs | Existing Task generation; periodic/sporadic and identity tests |
| 6. Actual scheduling trace | Engine intervals, releases, deadlines, switches, preemptions and terminal outcomes in Gantt/events |
| 7. Per-job policy/cost/admission explanation | Security audit, actual candidate objective/timing selection, snapshot bounds, costs and final reason |
| 8. Invalid messages never enter execution | Release-hook gates before admission; no-CPU/no-history assertions and all saved-run verification |
| 9. Honest misses and critical failures | Distinct gate/admission rejection, expiration, failure and safe-state counts; dedicated critical-outcome table |
| 10. Equivalent reproducible comparisons | Source-workload hashes, isolated receivers, paired seeded generator and documented history divergence |
| 11. Backend-derived metrics | Shared metric module plus explicit gate counts; no prefilled result cards |
| 12. New regression tests | Laboratory backend and Streamlit tests plus scheduler resume regression |
| 13. Existing security/health preserved | Optional context/hooks; default interfaces retained; full prior suite passing |
| 14. Full suite run | 235 passed, zero failed/skipped/warnings |
| 15. Documentation updated | README, laboratory guide, generated evaluation report and this delivery note |

## Architecture, use and limitations

[The laboratory guide](laboratory.md) contains the complete changed-file inventory,
architecture, time/event semantics, launch command, four-task security example,
preset parameters, metric denominators, export format and reproducibility commands.
The engine remains `RALPEDF`; the real gate coordinator remains `sensor_system`.
No duplicate scheduling framework or authentication pipeline was introduced.

Remaining limitations are explicit: configured costs are not hardware WCET;
finite released-job feasibility is not an arbitrary-future guarantee; MPS/SAEDF
baselines remain approximations; optional vehicle animation is omitted; GRU
requires real SKAB features/trusted commissioning and is not made to accept the
vehicle editor's distance-only input. Injected anomalous/unavailable health is
labelled simulated evidence, never a claimed real model classification. Actual
MAC/replay/session checks are still executed for those messages.

Independent runs do not share laboratory trust state. Comparison outcomes can
change subsequent accepted histories, so later eligibility may differ even when
the source workload and events are identical. A fixed editor workload does not
become a statistically new sample merely by changing its seed; the separate
repeated-trial control generates real seeded workload variation.
