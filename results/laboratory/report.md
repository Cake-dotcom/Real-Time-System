# Authenticated laboratory demonstration results

Actual runs through production authentication/health gates and the existing scheduler. Configured costs use milliseconds; RF is the vehicle baseline.

| Preset | Released | Completed | Gate rejected | Admission rejected | Missed deadlines | Safe-state events |
|---|---:|---:|---:|---:|---:|---:|
| Normal operation | 29 | 29 | 0 | 0 | 0 | 0 |
| Simultaneous arrivals | 29 | 29 | 0 | 0 | 0 | 0 |
| Critical pressure | 40 | 10 | 0 | 0 | 30 | 0 |
| Critical infeasibility | 40 | 10 | 0 | 10 | 20 | 10 |
| Tampered and replayed | 29 | 22 | 7 | 0 | 0 | 6 |
| Sensor fault | 29 | 23 | 6 | 0 | 0 | 6 |
| Risk escalation | 29 | 28 | 0 | 0 | 0 | 1 |
| Risk recovery | 29 | 29 | 0 | 0 | 0 | 0 |
| Overload | 40 | 10 | 0 | 10 | 20 | 10 |
| Periodic sensors | 29 | 29 | 0 | 0 | 0 | 0 |
| Security versus performance | 29 | 28 | 0 | 0 | 0 | 1 |

## Same-workload algorithm comparison

Security versus performance preset: same releases/events and seed; differing outcomes may change subsequent trusted histories.

| Algorithm | Released on time | Security overhead (ms) | Mean residual risk | Policy-relative compliance |
|---|---:|---:|---:|---:|
| Standard-EDF | 0.7241379310344828 | 127.640 | 0.07445796179368144 | 1.0 |
| Static-Sec-EDF | 1.0 | 980.780 | 0.041582989758975626 | 1.0 |
| MPS-LP-EDF-structural | 1.0 | 963.700 | 0.04157621430962546 | 1.0 |
| SAEDF-style | 1.0 | 980.780 | 0.041582989758975626 | 1.0 |
| RA-LP-EDF | 0.9655172413793104 | 415.380 | 0.0833836341573669 | 1.0 |

## Repeated seeded trials

Independent seeded source workloads; identical releases/events across algorithms per seed. Normal-approximation 95% CIs are exploratory, not a schedulability proof.

Three distinct seeds, 4 tasks, nominal base utilization .75, S4-spike, 3 algorithms, 9 runs. Each trace, source hash and configuration is saved in trials.json.

| Algorithm | On-time mean | Sample SD | Approximate normal 95% CI |
|---|---:|---:|---|
| Standard-EDF | 0.8906 | 0.0387 | [0.8468332871633817, 0.9344409941108995] |
| Static-Sec-EDF | 1.0000 | 0.0000 | [1.0, 1.0] |
| RA-LP-EDF | 1.0000 | 0.0000 | [1.0, 1.0] |

No hardware WCET, calibrated attack probability, infinite-horizon guarantee or uniform superiority is inferred. Rejected jobs are not counted as deadline misses. Structural MPS and single-CPU SAEDF are approximations. See docs/laboratory.md.
