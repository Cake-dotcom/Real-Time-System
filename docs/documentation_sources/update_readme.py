"""Documentation-only README update; existing text was inspected and backed up."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[2]
p=root/'README.md'
s=p.read_text(encoding='utf-8-sig')
s=s.replace('## Motivation and features', '''## Problem statement and objectives

The deadline budget must include authentication, validation and modeled protection overhead. A schedule based only on base computation can appear feasible while required security makes it late. The objectives are to preserve mandatory gates, adapt modeled protection to current risk, prioritize feasible critical work during overload, account for every fixed-point cost, and evaluate against explicit baselines on identical workloads.

The intended scenario is a research sensor-processing laboratory, not a certified vehicle controller. Water-testbed anomaly detection and legacy login risk remain separate experimental domains.

## Key features''')
s=s.replace('## Architecture and data flow', '''## Documentation deliverables

- [Presentation quick reference](docs/Presentation_Quick_Reference.pdf): five-page speaking guide.
- [Complete technical documentation](docs/Complete_Technical_Documentation.pdf): implementation, policy rules, examples and developer workflow.
- [Presentation flowchart](docs/Project_Workflow_Flowchart.png) and [editable Mermaid](docs/Project_Workflow_Flowchart.mmd).
- [Command contracts and verification status](docs/documentation_sources/Command_Reference.md): inputs, outputs, errors and which commands were actually executed.

## Architecture and data flow''')
s=s.replace('## Machine learning and domain boundaries', '''The sensor validation names are `standard`, `additional`, `enhanced`, `reject` and `unavailable`. They supplement mandatory MAC/replay, not replace it. The scheduler's `light`, `medium`, `strong` names denote modeled cost/protection levels. Legacy login actions (`password`, `password_plus_mfa`, `strong_mfa`, `throttle_and_strong_mfa`, `temporary_block`) are separate action descriptors; an interactive MFA provider is not implemented. See technical Chapters 9-10 for thresholds, checks and costs.

## Machine learning and domain boundaries''')
s=s.replace('## Repository structure', '''### Model protocol and verified saved results

Vehicle RF uses 300 balanced trees, seed 42, nine numeric/two categorical features and a grouped 25% run holdout. SKAB uses training-only scaling and overlap-group separation: 33,623 training, 4,863 validation and 5,153 test windows. The saved GRU has one layer, hidden size 32, window 20, dropout .2 and threshold .84, selected by validation before the held-out test. Saved GRU accuracy/macro-F1 are .8317/.8143 versus .8413/.8248 for the separate SKAB RF refit; this does not establish vehicle accuracy. The login model's original training/split provenance is not available.

## Repository structure''')
s=s.replace('## Run the dashboard', '''## First run

1. From the project root, create/activate the environment and install `requirements.txt` using the setup commands above.
2. Confirm the included `models/`, vehicle CSV and prepared SKAB files are present. Acquisition, preparation and retraining are **optional**, not prerequisites when included assets are intact.
3. Launch the dashboard below. Select **Normal operation**, run the laboratory, inspect actual gate outcomes and job deadlines.
4. Load **Tampered and replayed** to demonstrate mandatory rejection. Compare original and optimized on an unchanged workload.
5. Export JSON/CSV from the result tabs. For standalone login output, optionally run `python -m src.security.security_system`; it is a separate legacy simulation.

Every command below is root-relative. The [command ledger](docs/documentation_sources/Command_Reference.md) specifies required inputs, expected outputs, overwrite risks and verification status. Source/CLI verification is not claimed as a new network installation or training run.

## Run the dashboard''')
s=s.replace('## Security considerations and research limitations', '''## Example execution

**Saved authenticated trace:** `results/laboratory/normal_operation.json` records `T1:0` passing authentication/replay, with a 4 ms mandatory budget and completion at 416.41 ms simulated time. Only its successful, newer reading commits trusted history. Tampering after signing fails MAC before scheduling; a valid old packet can pass MAC but fail replay.

**Illustrative scheduler-only run:** this deliberately small input does not execute real message gates. With one light interval each, A completes at 2.081 and B at 3.142 simulation units. These are configured-cost calculations, not cryptographic measurements.

```python
from src.scheduler.model import Task, Phase
from src.scheduler.experiments import run_algorithm

tasks = [
    Task("A", (Phase("p", 2),), 10, 3, kind="oneshot"),
    Task("B", (Phase("p", 1),), 10, 5, kind="oneshot"),
]
trace = run_algorithm(tasks, [], "RA-LP-EDF-Optimized", horizon=10)
print([(j["job_id"], round(j["finish"], 3)) for j in trace["jobs"]])
# [('A:0', 2.081), ('B:0', 3.142)]
```

Run this from a root-level Python session, or execute `python docs/documentation_sources/verify_documentation.py` for the recorded documentation checks and example trace.

## Troubleshooting

| Problem | Remedy |
|---|---|
| Imports fail after cleanup | Recreate the environment; use its interpreter and pinned manifest. |
| Missing relative data/model path | Run from repository root; restore included artifacts. |
| GRU unavailable or history not ready | Check matching metadata/weights, SKAB feature order and trusted source/session/recording context. Never silently switch domains. |
| Replay/MAC/policy rejection | Inspect audit reasons; fix valid input/session state rather than bypass the gate. |
| Critical deadline failure | Read cost/blocking/risk events; criticality is not a feasibility guarantee. |
| Evaluation refuses overwrite | Preserve evidence and use a separate checkout or supported new output directory. |
| Dashboard cannot bind port | Choose another local port with `--server.port`; confirm required imports. |

## Research reproducibility

Preserve workload seeds, release/risk-event lists, unit conversions, policy/registry parameters, source hashes and model/split metadata. A Git HEAD alone does not identify uncommitted research code; archived source snapshots supplement it. Do not reuse held-out labels for threshold tuning. Frozen historical outputs remain evidence of their original version, not a new benchmark of later code. New experiments should use new directories or isolated checkouts.

## Security considerations and research limitations''')
s=s.replace('- `data/raw/login_activity.csv`: retained legacy login demonstration data.', '- `data/raw/login_activity.csv`: 15,000-row supplied legacy login CSV with normal/suspicious/brute_force labels. No official public source URL or redistribution permission is verified; do not assume it is public.')
s=s.replace('- `data/raw/skab/`: original SKAB CSVs', '- `data/raw/skab/`: original [SKAB repository](https://github.com/waico/SKAB) CSVs ([direct pinned data](https://github.com/waico/SKAB/tree/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/data))')
s=s.replace('## License and attribution', '''## Future work

Measure full execution/rejection costs on target hardware; strengthen durable key lifecycle/transport; collect independent domain-appropriate data; calibrate thresholds; evaluate future-arrival reservations and fairness; integrate a validated physical safe-state controller. These are proposed extensions, not implemented capabilities.

## License and attribution''')
heads=re.findall(r'^## (.+)$',s,re.M)
toc='## Contents\n\n'+'\n'.join('- ['+h+'](#'+re.sub(r'[^a-z0-9 -]','',h.lower()).replace(' ','-')+')' for h in heads)+'\n\n'
pos=s.index('## ')
s=s[:pos]+toc+s[pos:]
p.write_text(s,encoding='utf-8')
