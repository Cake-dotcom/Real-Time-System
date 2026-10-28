# Risk-aware limited-preemption scheduling

This extension studies whether changing simulated protection costs can reduce
overhead while retaining minimum protection and explicit timing checks. It does
not turn Python, Streamlit, learned health scores, or synthetic cost constants
into a certified real-time controller. The existing GRU and vehicle RF artifacts
remain unchanged. The legacy scheduler remains the default compatibility path;
select **RA-LP-EDF** under **Live scheduling algorithm** to use the new adapter.

## Architecture and security boundary

```
dashboard/app.py -> security/sensor_system.process_messages
  source/session authentication -> HMAC -> replay -> input/time checks
  -> RF or GRU health -> NIST-inspired validation policy -> required checks
  -> scheduler/sensor_adapter.schedule_sensor_tasks -> RALPEDF.run
  -> completed before deadline? -> commit accepted sensor history
```

The adapter receives only verified tasks. It cannot mark unauthenticated input
valid. Mandatory upstream validation and handshake budgets become an opaque
`mandatory_validation` phase, charged exactly once, separately from application
execution and optional simulated protection costs. Health prediction remains a
health assessment, never evidence that a source is cryptographically authentic
or that a measured attack probability is low. The receiver has no independent
threat feed, so the adapter uses **unknown exposure**, requiring strong modeled
protection. The synthetic laboratory supplies explicit exposure scenarios.

`sensor_system.process_messages(messages, scheduling_algorithm="RA-LP-EDF")`
is the production coordinator entry. Default `"legacy"` retains original tests,
interfaces and login/MFA behavior. Failed or deferred research jobs cannot commit
history. The adapter requests the existing safe-state response when critical
jobs fail; it does not implement physical actuator control.

## Task, job, and phase model

`model.py` validates unique task/phase identities, finite positive periods,
relative deadlines no larger than periods, release offsets, periodic and explicit
sporadic releases, minimum inter-arrival separation, criticality, minimum level,
phase costs, preemption caps and actual execution factors. A one-shot model
adapts sensor messages. Absolute deadlines are release plus relative deadline.
High/critical classification or `safety_critical=True` protects a task.

Jobs have independent cursors, state transitions, deadlines, cost ledgers and
preemption counts. Generated releases are strictly before the workload horizon;
execution then drains to terminal outcomes, potentially beyond that horizon.
Phases are ordered. A preemptible phase is split into equal fixed intervals no
larger than its quantum. A nonpreemptible phase is one interval. Preemption is
allowed only after teardown at an interval boundary; phase boundaries are also
eligible fixed points. A task's preemption cap can lock the entire remaining job.
This is single-processor scheduling without shared-resource locks or migration.

## Cost model and provenance

Each interval pays:

`base + base*execution_ratio + startup + teardown + switch + resume + decision`

Switch is charged only when changing mechanism after the initial choice; resume
only after an actual preemption. The outgoing job pays context-switch/preemption
cost once. Fixed-point teardown/startup is paid even if the same job continues,
as required by the static model. Accounting advances through ordered components,
so an interrupted interval pays only components already executed plus remaining
required teardown. Startup is not prorated across future computation.

`security_costs.py` supplies three **illustrative simulation configurations**:

| Mechanism | Level | Execution ratio | Startup / teardown / switch | Preempt / resume | Assumed effectiveness |
|---|---:|---:|---:|---:|---:|
| light | 1 | .02 | .02 each | .02 each | .25 |
| medium | 2 | .08 | .05 each | .02 each | .60 |
| strong | 3 | .16 | .10 each | .02 each | .90 |

All durations use abstract simulation units. These are not benchmarks, approved
cryptographic suites, or hardware WCETs. Effectiveness is an assumed reduction
factor, not a calibrated likelihood or security proof. Mechanisms contain an
explicit provenance field. The real HMAC/session layer remains separate. The
default simulated decision charge is .001 per dispatch; measured Python decision
wall time is reported separately and is not injected into simulation units.

An actual execution factor below one releases unused budget. A factor above one
causes a safe stop at the first exhausted configured interval; the simulator does
not continue overrunning and then claim an on-time completion. Obtaining hardware
WCETs requires platform-specific measurements and sound bounds, which are absent.

## Risk and bounded mechanism optimization

`dynamic_risk.py` uses exposure times impact in [0,1]. Missing, unconfident or
expired evidence yields risk 1. Defaults: risk below .3 requires level 1, below
.7 level 2, otherwise level 3, always at least the task/phase minimum. These are
documented scenario settings with sensitivity experiments, not NIST numerical
thresholds. Hysteresis .05 and dwell 5 delay downgrades only. Upgrades are immediate.

At a fixed point the scheduler enumerates the available mechanisms, removes those
below the required level or outside phase capabilities, and checks timing before
minimizing:

`alpha * risk * (1-effectiveness) + beta * overhead + gamma * switch_cost`

Defaults are alpha=1, beta=.15, gamma=.3. A compliant prior mechanism may remain
during dwell if it still passes timing checks. No dwell rule can suppress a
required upgrade. Enumerating three candidates bounds local selection work;
it is greedy for the current interval, **not globally optimal** over unknown
future risks/releases. The cost and residual-risk terms have different units,
so weights are scenario preferences, not a calibrated common monetary loss.

Alternatives considered: exhaustive joint phase assignments are exponential;
MILP/DP would require a specified finite threat horizon, discretization and solver
time bounds; cheapest-compliant selection ignores residual risk; strongest-feasible
selection ignores avoidable overhead. The implemented enumeration exposes all
three terms and is compared with strongest-feasible SAEDF-style behavior, fixed
security baselines, weight sensitivities and switching-awareness ablation.

## RA-LP-EDF execution and admission

1. Process completed intervals, then same-time risk events and releases.
2. Stop a running interval immediately if it is now under-strength; pay required
   cleanup and record failure/suspension. Do not restart partially computed work
   or pretend that stronger protection retroactively secured it.
3. Check remaining admitted demand. Shed lowest-criticality nonprotected waiting
   work first when configured overload handling is enabled. Never evict an
   admitted protected job simply to admit new work.
4. Consider pending/deferred jobs, protected first. Admit only when the released
   set passes the conservative deadline-prefix check. Reject impossible protected
   jobs with an explicit safe-state event; defer noncritical timing failures.
5. Maintain protected jobs' remaining demand by release/deadline. Their budgets
   reserve the maximum cost of all currently compliant mechanisms at each future
   interval, including switching, resume and preemption allowances. New work must
   fit alongside these reservations. There is no independent double debit of
   reservations: they are the same execution bounds used in admission.
6. Select the earliest absolute deadline among active jobs, using criticality only
   for ties. Continue the current job if preemption is prohibited or its cap is
   reached; account for its entire locked suffix in subsequent admissions.
7. Choose a feasible compliant mechanism, execute to the next fixed point/event,
   and debit component costs. Reconsider deferred jobs when capacity changes.

The ledger is a deadline-indexed demand reservation, **not a CBS server** or an
OS-enforced temporal partition. It reserves released protected jobs, not a future
periodic server budget. If their risk/cost assumptions cease to hold, explicit
failure is possible. Reservations do not guarantee that every future critical
arrival is admitted. Configurable ablations can remove admission or reservations;
such runs deliberately weaken timing assurance while retaining minimum security.

## Two separate feasibility claims

### Released-job check

`released_job_feasibility` accumulates conservative remaining bounds in EDF
deadline order, preceded by unavoidable current blocking. The current interval
is removed from its job's suffix so it is paid once. When preemption is capped,
the entire remaining locked job is blocking. Every prefix must finish by its
deadline. Finite, independent jobs with no further releases/risk changes, bounded
component costs, and the modeled preemption rules satisfy this sufficient serial
envelope. It can reject feasible schedules because transition bounds and blocking
are pessimistic. It is **not an infinite sporadic schedulability certificate**.
Admission is rechecked at runtime events. Unexpected execution demand, threats,
or future critical arrivals can invalidate assumptions and trigger safe failure.

### Static published-model analysis

Official source: Standaert et al. (2025), *Limited-Preemption EDF Scheduling for
Multi-Phase Secure Tasks*. [DOI and official publication](https://drops.dagstuhl.de/entities/document/10.4230/LITES.10.1.3).
The [official full text](https://drops.dagstuhl.de/storage/07lites/lites_vol010/lites_vol010_issue001/html/LITES.10.1.3/LITES.10.1.3.html)
defines the model in **Section 2**, fixed-point cost behavior in **Section 3.2**,
and the schedulability/count construction in **Sections 4.1–4.3**, using corrected
**Equation (9)** rather than the earlier blocking condition.

`feasibility.mps_analysis` implements static demand-bound testing and equal
subdivision counts. It distinguishes infeasible from unknown testing limits.
Additional per-interval costs are conservatively folded into its transition
bound; per-dispatch decision cost is outside its certificate. Nonzero extra costs,
runtime selection and capped preemption prevent transferring the publication's
optimality claims to the complete engine. Tests include a hand-derived subdivision
and a corresponding static periodic execution. This is not an independent formal
verification or an exhaustive reproduction of the paper's evaluation.

Static assumptions: independent constrained-deadline uniprocessor tasks; known
bounded execution and transitions; fixed security choices; fixed equally spaced
phase points; enough allowed preemptions; no resource locking, risk changes,
unmodeled scheduler overhead or suspensions. Analysis returns unknown when its
testing-set budget is exceeded, when a configured cap restricts required points,
or when the implemented finite bound cannot cover utilization-one noninteger
periods. An analysis result never certifies the dynamic-risk adapter.

## Comparisons and reproducibility

All algorithms receive the same source workload and risk-event hash, seed and
release population. Policy-specific checkpoint placement is explicit:

| Label | Implemented semantics | Fidelity limitation |
|---|---|---|
| Standard-EDF | Fixed light protection; 1-unit checkpoints; no admission/reservations/overload | Discrete approximation of preemptive EDF; refuses under-strength execution |
| Static-Sec-EDF | Fixed strong protection; same 1-unit checkpoint approximation | Costs paid at every checkpoint; not a zero-overhead ideal EDF |
| MPS-LP-EDF-structural | Fixed strong mechanism; static-derived counts when analysis succeeds; original points otherwise | Conservative transition extras and online admission remain; no claim of faithful full paper reproduction |
| SAEDF-style | Highest feasible security at each selection on shared engine | Single processor approximation; not original cluster SAREC |
| RA-LP-EDF | Dynamic risk, bounded objective, configured fixed points, admission/reservations | Greedy finite-release policy, no global optimality claim |

SAEDF motivation comes from Xie and Qin, *Scheduling Security-Critical Real-Time
Applications on Clusters*, **Sections 3–5**, especially the security-cost model
and SAEDF scheduling strategy. [Authors' paper](https://taoxie.sdsu.edu/publication/tc06.pdf).
Its cluster setting differs from this implementation; results cannot establish
superiority over the original published scheduler.

The generator uses bounded random utilization weights (not UUniFast), periods
100/125/200, mixed periodic/sporadic arrivals, implicit/constrained deadlines,
1–6 phases and a default 25% protected share. Target utilization is **base work**,
excluding security and scheduler costs; S7 multiplies base demand by 1.5. Scenarios
cover low/high, gradual increase, one-task spike, recovery, multiple exposed tasks
and overload. The full grid covers n=4/8/12/16/20 and U=.2/.5/.75/.95 with five
paired seeds, all seven scenarios and five algorithms. Sensitivities vary risk,
overhead and switching weights, thresholds, costs, phase count, protected share,
execution factor and caps. Ablations disable dynamic updates, switching awareness,
preemption, admission, reservations and overload independently. Ablation summaries
use the multiple-exposure workload; they do not cover the entire Cartesian grid.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -u -m src.scheduler.experiments --full --workers 4
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

Use `--workers 1` for sequential wall-latency measurements, `--output PATH` for a
separate result directory, and omit `--full` for a smaller sweep. Main results
record worker concurrency; sensitivity runs are sequential. Runtime under worker
contention is a measured wall latency, not standalone processor WCET.

Saved JSON includes every source workload, raw run metrics, representative full
traces, per-configuration means/sample standard deviations/approximate normal
95% intervals, paired RA-minus-baseline differences, sensitivity runs, environment
and SHA-256 source hashes. Five seeds give exploratory estimates; normal intervals
can cross logical metric bounds and are not a significance proof. Variability is
computed across seeds at a fixed scenario/size/utilization, not by pretending
different workloads are repeated measurements of the same configuration.

## Metric definitions

Released-job denominators include rejected, deferred-until-expiry and failed work.
Deadline-miss ratio counts jobs ending `deadline_missed` / released jobs; it does
not count immediate rejection as a deadline miss. Critical misses use all critical
releases. Critical rejection/failure/completion counts are separate. Released
on-time ratio counts completed / released; admitted on-time ratio uses all jobs
ever admitted. Always inspect acceptance/completion with misses. Empty denominators
return JSON null, never manufactured zero or perfect success.

Response time is finish minus release for completed jobs only, with mean, maximum
and nearest-order p95. CPU utilization is summed component costs / observation
interval; the latter is max(horizon, last event), and idle is its complement.
Security overhead excludes application base and scheduler decision charge but
includes mandatory-validation budgets. Component ledgers distinguish every cost.
Residual-risk integral weights modeled execution time by risk*(1-effectiveness);
its mean and compliance exclude idle and cleanup. These execution-conditioned
metrics are subject to selection bias if work is rejected, so completion must be
reported alongside them. Switching/preemption counts are actual events.
Compliance and risk use each run's active policy view. The `no_dynamic` ablation
intentionally ignores new exposure events; its policy-relative compliance does
not prove compliance with the external changing threat scenario. Its increased
completion must not be interpreted as a secure improvement.

Rejection ratio is final rejections / releases; ever-deferred ratio counts unique
jobs with deferral events / releases. Recovery durations span explicit overload
and recovery events. An overload still active at run end has no recovery sample.
Reservation utilization is debited work / cumulative reserved increases, with
negative-budget violations counted. Scheduler wall time measures admission and
dispatch code; simulation wall time includes event processing. Neither includes
real deployment interrupt latency. `formal_dynamic_schedulability` is always null.

## Remaining work, in priority order

1. Establish deployment-specific execution/crypto WCET bounds, interrupt costs and
   safe-stop actuation requirements; replace abstract cost units only with evidence.
2. Add recurring critical-server reservations and prove admission across future
   sporadic arrivals and bounded risk trajectories. The current finite ledger is
   useful but not that guarantee.
3. Independently validate the static analysis against the authors' implementation
   and reproduce faithful MPS and cluster-SAEDF comparisons before publication.
4. Calibrate exposure/effectiveness using threat evidence distinct from health ML;
   integrate trusted risk feeds with freshness and provenance.
5. Expand repetitions, sensitivity interactions and hardware latency experiments;
   investigate lookahead optimization only after the timing bounds are credible.

The dashboard displays actual job outcomes, timelines, risk, cost/seed settings,
admission and reservation logs, and saved baseline means. It does not render a
formal proof, execute new crypto mechanisms, or expose every simulator parameter
as an editable UI control.
