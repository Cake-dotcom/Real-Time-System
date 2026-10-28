# Deadline optimization delivery

The existing event-driven scheduler now offers three optional strategies. The original RA-LP-EDF remains the default and reproduces its saved pre-change behavioral traces exactly on all 200 benchmark workloads. No task budget, release, deadline, security cost, model weight or authentication rule was changed to obtain the reported gains.

## Measured result

Each row aggregates 40 identical paired workloads: seeds 101–120, task counts 4 and 12, release horizon 200. The existing generator mixes periodic/sporadic releases, constrained deadlines and one to six phases. There are 543 releases and 132 protected releases per row. Protected means safety_critical or critical/high criticality; the generator can flag a task protected while its textual criticality remains normal.

| Scenario | Original → optimized on time | Original → optimized critical on time | Completion change | Security overhead change |
|---|---:|---:|---:|---:|
| Normal, base utilization .50 | 543 → 543 | 132 → 132 | 0% | −67.50% |
| High load, base utilization .85 | 543 → 543 | 132 → 132 | 0% | −50.38% |
| High risk, base utilization .85 | 539 → 540 | 131 → 132 | +0.19% | +0.09% |
| Unexpected risk spike, utilization .85 | 534 → 534 | 123 → 123 | 0% | −38.12% |
| Overload, base utilization .95 × 1.5 | 407 → 440 | 116 → 132 | +8.11% | −26.50% |

Overload completion rises from 74.95% to 81.03% (+6.08 percentage points); critical completion rises from 87.88% to 100% (+12.12 points, +13.79% relative). The seed-paired mean completion-ratio improvement is 5.75 points, approximate 95% interval [4.03, 7.47]. This differs from the pooled ratio because each seed/size pair receives equal weight. Estimates use 20 seed clusters, averaging the two sizes within each seed, sample SD and normal confidence intervals. Synthetic samples are not deployment evidence.

All seven requested strategies are reported in [the generated report](../results/optimization/report.md). [comparison.csv](../results/optimization/comparison.csv) includes absolute values, deltas and relative percentages; [paired_statistics.json](../results/optimization/paired_statistics.json) includes variability. The comparison uses original-mode runtime measured alongside the candidates, rather than mixing pre-change timing with a different run's contention. Final measurements show lower decision time in four groups, but **13.71% higher decision time in the high-risk group**. Do not infer a universal speedup or a hardware WCET from Python latency.

The 44 authenticated runs (11 existing presets × original plus three strategies) are in [laboratory/summary.json](../results/optimization/laboratory/summary.json). These presets show unchanged completion counts: for example normal 29/29, risk escalation 28/29, and critical infeasibility 0/10 critical jobs under both original and combined modes. Thus the synthetic overload improvement is not misrepresented as an improvement on every dashboard preset.

## Bottlenecks and decisions

Original admission greedily committed to deadline order, potentially retaining one long job instead of two short jobs, and could reject new protected work behind reclaimable normal demand. Protected budgets reserved the maximum cost of every eligible mechanism for every remaining interval. Mechanism selection used a residual-risk/overhead weighted score. Every EDF change of running job could interrupt it even when the waiting job could safely wait. Repeated budget construction dominated standalone scheduler profiling.

* **RA-LP-EDF-Admission:** select a feasible protected subset first, then use spare capacity for noncritical jobs. For up to eight optional jobs per pass, enumerate subsets by descending cardinality; deterministic ties retain admitted jobs, then prefer smaller demand and older releases. Larger populations use bounded EDF insertion and largest-demand exchange. This is a released-job heuristic, not a global optimum. Running atomic intervals and capped/nonpreemptible work remain pinned. Displaced normal jobs are deferred and retried at subsequent events; interruption is charged once when their running suffix is reclaimed at a fixed point. An infeasible protected bound produces an explicit safe-state outcome.
* **RA-LP-EDF-Preemption:** retain the previous job only when its entire remaining conservative budget can finish first and the remaining EDF envelope still meets every released deadline. Recheck at each event/fixed point. No preemption point is moved, and no atomic interval is interrupted. This conservative rule is intentionally stronger than merely checking the arriving job's deadline.
* **RA-LP-EDF-Optimized:** combine subset admission and limited interruption with a compliant continuation budget under current risk evidence. Choose the least full-cost eligible current interval that has a feasible continuation, subject to dwell. Costs include execution, startup, teardown, applicable switch/resume and scheduler charge. Planning retains conservative per-interval switch/context allowances. Projected dwell uses base-only elapsed execution, which conservatively delays downgrade. Mandatory validation remains an actual upstream gate and a separately charged phase.
* All new modes cache budgets only inside one decision epoch. Keys include cursor, mechanism, last switch, resume flag, preemption count, plan length and candidate override. Every external/risk/release/completion event clears the cache before admission. Cached/uncached traces are tested for exact equivalence across five seeded scenarios. There is no reused authentication verdict or skipped MAC/replay check.

Setup/teardown is still charged at every fixed interval. The model does not permit amortizing it, so it was not removed. Reservations represent the selected remaining protected demand; they are not a replenishing CBS server or advance reservations for unreleased jobs. No future risk-event knowledge is used in decisions.

## Security and important counterexample

The dashboard path is `show_laboratory → compare/run → SecurityRuntime.release → sensor_system.process_messages(prepare_only=True) → run_algorithm → RALPEDF`. Only gate-eligible messages enter scheduler admission; only on-time completions call `SecurityRuntime.complete` to commit trusted history. Optimized policy code never supplies alternative authentication, replay or health results.

All executing intervals in the evaluated traces comply with the active required security level. A risk increase inside an under-strength atomic interval invokes the existing suspension/fail-stop/cleanup response. Downgrade respects hysteresis and dwell. Unavailable health evidence, bad MACs and replays cannot enter the CPU or trusted history in the integration tests.

**Least cost does not mean maximum protection against unknown future threats.** In the explicit [unexpected-spike counterexample](../results/optimization/laboratory/unexpected_spike_tradeoff.json), a critical job with base cost 1, deadline 5 and risk spike at .1 completes under original RA (which happens to select strong initially), but safely fails under optimized RA (which selects initially sufficient light protection). This is a real critical regression, covered by a regression test, even though none of the 200 random benchmark pairs showed a combined-mode critical-count regression. Residual risk may increase when optional stronger protection is removed. The original remains the default; use the side-by-side comparison and workload-specific risk requirements before selecting the optimized mode.

## Metrics and failure diagnosis

Full traces include every release, admission, deferral, dispatch, actual interval, switch, interruption, completion, rejection and safe state. Snapshots expose absolute deadline, remaining base/security bound, slack, required level, current mechanism, admission, reservation and preemption history. The combined dispatch explanation identifies whether EDF, a cap, or the continue-current bound selected the job.

On-time completion uses all released jobs as its denominator. `critical_on_time_ratio` uses all protected releases. Existing `deadline_miss_ratio` counts deadline-expired states only; `noncompletion_ratio` and `critical_noncompletion_ratio` also include rejection/fail-stop. `admitted_noncompletion_jobs` and `never_admitted_jobs` distinguish failures after admission from unadmitted work. `infeasible_admissions` counts admission events that explicitly failed the sufficient test (expected in baseline modes that disable admission); a later risk invalidation is not retroactively counted as an infeasible original admission. Textual criticality breakdown is separate from the protected flag.

`cost_categories` reports base, validation, security execution, startup, teardown, switching, preemption, resume and simulated scheduler cost. `security_overhead` includes all except base and scheduler. Residual risk is the wall-time integral of exposure × impact × (1 − configured effectiveness), divided by executing protected-mechanism time; it is not an attack probability. Compliance is modeled executing time at or above the active requirement divided by that time. Idle time and utilization use max(release horizon, drain end). Python decision and whole-simulation latency are separate from simulated demand. Rejected-message gate work affects Python latency but is not charged to the simulated CPU, as in the existing model.

[all_misses.jsonl.gz](../results/optimization/all_misses.jsonl.gz) and [critical_misses.jsonl.gz](../results/optimization/critical_misses.jsonl.gz) retain exact per-job event evidence, final reason, a phase-minimum cost lower bound, measured noncritical overlap and algorithms that completed the same job. A base or mandatory-cost lower bound exceeding the individual deadline proves individual infeasibility. A failed sufficient admission envelope alone does **not** prove inherent infeasibility. Alternative completions indicate a possible scheduling trade-off, not necessarily a dominating whole-workload schedule. The report deliberately leaves admission/interference attribution unresolved where evidence cannot distinguish it. It does not invent causes such as excessive switching, late release or implementation bugs merely because a job failed. Late-horizon releases drain normally and retain release + relative deadline accounting.

## Verification and reproducibility

Before changing engine code: **235 tests passed**, then **800 baseline runs** were saved with the source unchanged during evaluation. Baseline directory contains `tests.log`, `source.zip`, `metadata.json`, a profile and compressed full traces including exact task sets/risk events. Metadata records SHA-256 hashes of source/tests, Git HEAD, Python/platform, seeds, policy, registry scale and checkpoint. The working tree already contained substantial prior work; the source archive, not HEAD alone, is the reproducibility reference.

The final main evaluation contains another 800 runs (original RA plus three strategies). Audits reproduce original jobs/events/timeline/reservations/risk history exactly, check serial CPU execution, cost conservation, on-time timestamps and mandatory compliance. Initial optimized results are preserved separately in `optimized-initial`; use `optimized` for final comparisons. The end-to-end laboratory runs additionally audit real gate rejection and trusted-history commits. `laboratory/profiles.txt` separates full pipeline and standalone scheduler profiles: health inference dominates the full pipeline, while budget/check work dominates original scheduler work. Profile timings include instrumentation overhead and are not directly interchangeable with benchmark latency.

Final validation: **278 passed in 48.13 seconds; no failures**. Output is saved in `results/optimization/tests.log`. Tests cover each new policy, real tamper/replay and faulty/unavailable health gates, fixed-point/cap restrictions, reclaimed critical capacity, exact interruption/setup/switch/resume accounting, current-risk reservation bounds, safe overload, periodic progress, horizon drain, dwell and risk escalation, reproducibility, and the live dashboard comparison. Existing authentication, GRU, scheduling and dashboard tests remain part of the full suite.

From the project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe scripts/benchmark_optimization.py baseline --workers 4 --seeds 20
.\.venv\Scripts\python.exe scripts/benchmark_optimization.py optimized --workers 4 --seeds 20
.\.venv\Scripts\python.exe scripts/report_optimization.py
.\.venv\Scripts\python.exe scripts/evaluate_optimized_laboratory.py
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

Benchmark commands intentionally refuse to overwrite saved main-stage results. Preserve or explicitly move their stage directories before a new experiment. To reproduce the exact pre-change implementation, unpack the baseline source archive into a separate working directory with the same dependencies. In the dashboard select **Compare algorithms**, select **RA-LP-EDF** and **RA-LP-EDF-Optimized**, run the unchanged configuration, then open **Algorithm Comparison**. It shows both actual Gantts and critical/total completion counts, and warns if optimized critical completion worsens.

## Exact implementation files

Modified: `src/scheduler/ra_lp_edf.py`, `src/scheduler/dynamic_risk.py`, `src/scheduler/experiments.py`, `src/scheduler/scheduling_metrics.py`, `src/dashboard/laboratory.py`, `tests/test_laboratory_dashboard.py`, `README.md`.

Added: `src/scheduler/optimization.py`, `tests/test_scheduler_optimization.py`, `scripts/benchmark_optimization.py`, `scripts/report_optimization.py`, `scripts/evaluate_optimized_laboratory.py`, this document, and `results/optimization/` evidence. No security gate, health-model implementation, model artifact or workload preset was changed by this task.

## Limits

There is no infinite-arrival guarantee, global optimality claim, future-risk oracle or promise that every critical deadline survives arbitrary overload. Small subset search is exact only for its current optional population and fixed pinned set; larger searches and continuation planning are heuristics. Already-running atomic intervals can still block newly released critical jobs. Future protected releases are not reserved ahead of time. Optional stronger security can have higher resilience but also higher cost; mandatory security is never relaxed. Some presets remain inherently or conservatively infeasible. The simulation costs are configured estimates, not measured deployment WCETs. These limitations remain visible rather than being removed through friendlier defaults.
