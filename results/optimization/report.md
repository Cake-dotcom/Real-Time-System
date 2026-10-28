# Paired optimization results

20 seeds × two sizes (4,12) per scenario. Horizon 200; unchanged workload generator. Full inputs, policy, source archives and traces accompany results.

| Scenario | Algorithm | All on time | Critical on time | Security overhead | Preemptions | Scheduler ms |
|---|---|---:|---:|---:|---:|---:|
| S1-low/U=0.5 | RA-LP-EDF | 543/543 | 132/132 | 526.18 | 11 | 1977.8 |
| S1-low/U=0.5 | Standard-EDF | 543/543 | 132/132 | 297.28 | 15 | 4664.5 |
| S1-low/U=0.5 | Static-Sec-EDF | 543/543 | 132/132 | 1745.04 | 21 | 4474.6 |
| S1-low/U=0.5 | MPS-LP-EDF-structural | 543/543 | 132/132 | 1071.60 | 10 | 764.2 |
| S1-low/U=0.5 | RA-LP-EDF-Admission | 543/543 | 132/132 | 526.18 | 11 | 1099.4 |
| S1-low/U=0.5 | RA-LP-EDF-Preemption | 543/543 | 132/132 | 525.74 | 0 | 1027.7 |
| S1-low/U=0.5 | RA-LP-EDF-Optimized | 543/543 | 132/132 | 171.00 | 0 | 1153.9 |
| S1-low/U=0.85 | RA-LP-EDF | 543/543 | 132/132 | 502.09 | 22 | 2807.2 |
| S1-low/U=0.85 | Standard-EDF | 543/543 | 132/132 | 482.61 | 24 | 10871.4 |
| S1-low/U=0.85 | Static-Sec-EDF | 487/543 | 115/132 | 2724.65 | 5 | 12640.0 |
| S1-low/U=0.85 | MPS-LP-EDF-structural | 539/543 | 131/132 | 1671.43 | 7 | 1706.1 |
| S1-low/U=0.85 | RA-LP-EDF-Admission | 543/543 | 132/132 | 502.09 | 22 | 1607.2 |
| S1-low/U=0.85 | RA-LP-EDF-Preemption | 543/543 | 132/132 | 501.21 | 0 | 1468.5 |
| S1-low/U=0.85 | RA-LP-EDF-Optimized | 543/543 | 132/132 | 249.13 | 0 | 1790.8 |
| S2-high/U=0.85 | RA-LP-EDF | 539/543 | 131/132 | 1671.43 | 7 | 1295.8 |
| S2-high/U=0.85 | Standard-EDF | 0/543 | 0/132 | 0.00 | 0 | 41.2 |
| S2-high/U=0.85 | Static-Sec-EDF | 487/543 | 115/132 | 2724.65 | 5 | 11939.8 |
| S2-high/U=0.85 | MPS-LP-EDF-structural | 539/543 | 131/132 | 1671.43 | 7 | 1599.9 |
| S2-high/U=0.85 | RA-LP-EDF-Admission | 540/543 | 132/132 | 1673.30 | 9 | 1063.2 |
| S2-high/U=0.85 | RA-LP-EDF-Preemption | 539/543 | 131/132 | 1671.15 | 0 | 891.9 |
| S2-high/U=0.85 | RA-LP-EDF-Optimized | 540/543 | 132/132 | 1672.98 | 1 | 1473.5 |
| S4-spike/U=0.85 | RA-LP-EDF | 534/543 | 123/132 | 620.92 | 21 | 2754.7 |
| S4-spike/U=0.85 | Standard-EDF | 495/543 | 84/132 | 423.10 | 23 | 10151.7 |
| S4-spike/U=0.85 | Static-Sec-EDF | 487/543 | 115/132 | 2724.65 | 5 | 13176.3 |
| S4-spike/U=0.85 | MPS-LP-EDF-structural | 539/543 | 131/132 | 1671.43 | 7 | 1846.6 |
| S4-spike/U=0.85 | RA-LP-EDF-Admission | 534/543 | 123/132 | 620.92 | 21 | 1677.1 |
| S4-spike/U=0.85 | RA-LP-EDF-Preemption | 534/543 | 123/132 | 620.08 | 0 | 1411.2 |
| S4-spike/U=0.85 | RA-LP-EDF-Optimized | 534/543 | 123/132 | 384.21 | 0 | 1715.0 |
| S7-overload/U=0.95 | RA-LP-EDF | 407/543 | 116/132 | 386.61 | 6 | 4721.4 |
| S7-overload/U=0.95 | Standard-EDF | 339/543 | 80/132 | 594.20 | 2 | 28098.8 |
| S7-overload/U=0.95 | Static-Sec-EDF | 236/543 | 53/132 | 2749.37 | 2 | 21622.1 |
| S7-overload/U=0.95 | MPS-LP-EDF-structural | 354/543 | 121/132 | 1645.85 | 2 | 2373.1 |
| S7-overload/U=0.95 | RA-LP-EDF-Admission | 429/543 | 132/132 | 411.70 | 11 | 2934.5 |
| S7-overload/U=0.95 | RA-LP-EDF-Preemption | 407/543 | 116/132 | 386.49 | 3 | 1891.1 |
| S7-overload/U=0.95 | RA-LP-EDF-Optimized | 440/543 | 132/132 | 284.17 | 3 | 2868.5 |

Critical regressions versus original RA: 186 algorithm/workload pairs, listed explicitly in critical_regressions.json. Combined optimized mode: 0 pairs.

Paired statistics use each seed's mean across the two sizes (20 independent seed clusters), sample SD and approximate normal 95% intervals. These synthetic scenarios do not establish deployment guarantees. Runtime includes concurrent-process contention.

Critical miss records retain exact per-job event evidence. A failed sufficient admission test alone is NOT proof of inherent infeasibility. Static EDF and MPS use their documented checkpoint transformations; adaptive modes use identical fixed points.

Audit passed: saved original RA behavioral traces reproduced exactly; all reported completions meet deadlines; timeline is serial; charged costs conserve CPU time; executing protection complies with current policy.