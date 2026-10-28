# Master-request audit and traceability

Baseline before scheduler changes: 148 tests passed in 37.15 seconds.
Existing changes from dataset/GRU stages are preserved; no artifacts are overwritten.

Active imports: dashboard -> sensor_system -> scheduler.schedule_message_tasks.
GRUHealthMonitor is active; SensorHealthMonitor is the explicit vehicle RF baseline.
security_system retains the login/MFA path. RiskEngine is login-specific; risk_policy
is the NIST-inspired sensor evidence policy. These are different domains, not duplicates.
The old non-preemptive scheduler remains a labelled compatibility baseline.

| Request sections | Existing evidence / gap | Planned implementation | Verification required |
|---|---|---|---|
| 1–4 | Existing session/HMAC/replay/GRU/policy tests; single-pass EDF | Separate research scheduling layer and protected adapter | Full regression and adapter gate tests |
| 5 | Flat one-shot dictionaries only | Validated Task/Job, releases, state machine | Periodic/sporadic, identity, transition tests |
| 6–7 | Single execution/security cost | Fixed-point phases and canonical component costs | Hand-calculated three-phase and preemption costs |
| 8–9 | Non-preemptive EDF only | Event-driven RA-LP-EDF; static published-model analysis | Allowed/forbidden preemption, blocking tests |
| 10–12 | Retry critical-only workload | Released-job feasibility, critical demand ledger, deferral/recovery | Threatening admission, critical overload, reservations |
| 13–17 | Qualitative sensor risk only | Separate exposure*impact evidence, expiry, minimum levels, bounded optimization | Spikes, stale evidence, hysteresis, no downgrade |
| 18 | No schedulability analysis | Corrected demand/blocking test and finite-job conservative admission | Static examples; explicit scope of guarantees |
| 19 | Deadline result only | Cost/event/response/risk/reservation metrics | Conservation, denominators, empty workloads |
| 20 | Old EDF baseline | Shared simulator with explicit structural baselines and reference restrictions | Paired identical workload hashes |
| 21–22 | No scheduler experiment harness | Seeded workload scenarios, ablations, sensitivity, aggregates | Actual raw results and variability |
| 23–24 | Working live dashboard/security gates | Opt-in research adapter plus real scheduling panel | AppTest and security integration |
| 25 | 148 regression tests | Focused unit/integration and seeded invariant tests | Full suite and reported failures |
| 26–29 | Prior-stage documents | Research/design note, measured report, file inventory, limitations | Artifact verification; no unsupported formal claims |

This is the pre-implementation map. Final completion statuses and measured evidence
are in [the delivery report](scheduling_completion.md) and
[the measured evaluation](../results/scheduling/evaluation_report.md).
