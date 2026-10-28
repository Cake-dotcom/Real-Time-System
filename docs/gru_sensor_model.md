# GRU sensor anomaly detector

Final measured results are in [evaluation_report.md](../results/gru/evaluation_report.md).
Final full regression: **148 passed, zero failed, in 40.98 seconds**. The original
RF artifact and vehicle dataset SHA-256 checksums remain unchanged. The trained
GRU also produced an accepted nominal result through the complete live pipeline;
see [backend audit example](../results/gru/live_pipeline_example.json).
Every stage file and verification outcome is listed in
[verification.json](../results/gru/verification.json).

Tests include CPU training/checkpoint roundtrip, malformed/missing features,
metadata and checksum failures, short histories, session/run isolation, batch
chronology, MAC tampering/replay/unknown sources, session reuse/expiry/revocation,
unhealthy evidence despite passing additional checks, missing/invalid model
evidence, deadline rejection and accepted-history isolation. All prior login/MFA,
policy, scheduling and dashboard tests remain in the full suite.

## Scope and sources

This stage uses Skoltech Anomaly Benchmark (SKAB v0.9), Katser and Kozitsin (2020),
DOI https://doi.org/10.34740/KAGGLE/DSV/1693952 . See
[dataset documentation](../data/SKAB_DATASET.md) for license, pinned source,
features, recording overlap and annotation conflicts.

Implementation references: [PyTorch GRU](https://docs.pytorch.org/docs/stable/generated/torch.nn.GRU.html),
[PyTorch previous-version installation](https://pytorch.org/get-started/previous-versions/),
and [scikit-learn GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html).
The classifier is unidirectional: its target is the current window endpoint.
Binary classes are normal and anomalous; there is no faulty subclass or malicious
source attribution. No augmentation was performed.

## Experiment protocol

All candidates use the dataset-stage endpoint population and unchanged component
split: training 25 files / 20 components / 33,623 windows; validation 5 files /
5 components / 4,863 windows; test 5 files / 5 components / 5,153 windows.
The sequence loader checks checksums, schema, finite values, order, component
isolation, gaps and ambiguous-target masks. It never sorts shuffled rows into an
invented sequence. Shorter candidate windows use the final 20 of each existing
64-observation window, so every candidate and the tabular RF see identical targets.

Eight physical features in the original order are used; no labels, change-point
annotations, recording IDs or future statistics enter the network. Dataset-stage
training-row mean/std are reused unchanged. There are no categorical features.
Chronology allows one/two-second steps and no longer gaps, without resampling.

Predeclared candidates: hidden size 32 / length 20; hidden size 64 / length 20;
hidden size 64 / length 64. Each uses one `torch.nn.GRU` layer, dropout 0.2 on
the final hidden state, then a two-logit linear head. AdamW learning rate 0.001,
weight decay 0.0001, batch 256, maximum 30 epochs, patience 5, gradient norm
clipping at 1.0. Inverse-frequency class weights come only from training targets.
Invalid targets, empty splits, nonfinite loss/outputs/gradients stop training.
Seed 42 controls Python, NumPy and PyTorch; deterministic algorithms and fixed
CUDA workspace are enabled. Exact reproduction across hardware/releases is not promised.

At every epoch, choose a threshold on the fixed validation grid 0.05..0.95 in
0.01 steps to maximize macro-F1. Save the best validation epoch, select the best
candidate by its validation macro-F1, then freeze checkpoint/threshold before
test evaluation. This balances class performance, not an application-certified
cost of missed faults. Deployment threshold costs require a separate validation
study. Softmax scores with weighted loss are not calibrated risk probabilities.

The existing RF classifier is cloned with its original 300-tree, balanced-class,
seed-42 settings and refitted to the eight current-observation features at exactly
the same endpoints. Its threshold is selected on validation by the same rule.
The original vehicle RF and artifact remain available; they cannot honestly be
evaluated on SKAB without retraining because their feature space and classes differ.
Its separate reconstructed vehicle holdout diagnostic is retained under
`results/gru/legacy_rf/`, not placed in the SKAB comparison as equivalent evidence.

Three GroupKFold diagnostics use only the 20 training components, keeping overlap
components intact. Each fold refits its own scaler on fold-training window
contexts after undoing the global transform; repeated contexts affect weighting.
Fold epochs are capped at 15. Their checkpoint and threshold use that fold's
validation data, so these are explicitly **inner validation diagnostics**, not
unbiased nested cross-validation results. Only the untouched final test supports
the reported held-out comparison. Five held-out components are a small sample;
window-level scores are not independent-trial uncertainty estimates.

An additional `cross_validate_gru` command performs three **outer group checks**:
each held-out training component is scored only after fitting on the remaining
training components, with the original separate validation split used for early
stopping/thresholds. Outer fold labels never select checkpoints or thresholds.
These results are in `outer_group_evaluation.json`; they do not replace or tune the
final test. The original inner diagnostics remain labelled as such for transparency.

Epoch logs, selection metadata, per-class metrics, confusion matrices, per-group
metrics, precision-recall curves, endpoint predictions and timings are written to
`results/gru/`. The evaluation command refuses to overwrite an existing test report.
Training restarts deterministically rather than resuming an optimizer checkpoint;
completed inference checkpoints remain usable without the dataset.

## Runtime interface and security

The live `sensor_system.health_monitor` is `GRUHealthMonitor`. The retained
`SensorHealthMonitor` class is the explicit vehicle RF baseline, also selectable
in the dashboard. There is no automatic RF fallback when GRU evidence is missing.

The GRU requires signed message fields `sensor_domain="SKAB"`, `recording_id`,
`timestamp`, and `sensor_values` containing the exact eight feature names. The
existing source/session/sequence fields remain mandatory. HMAC covers the whole
message, including all physical values and identifiers. `distance_m` is still
separate simulator evidence used by the existing deterministic policy; it is not
converted into a SKAB feature. `SKAB_01` is a provisioned demonstration source with
criticality 1; its demo key has the same non-production status as other demo keys.
The existing distance-derived policy checks are retained, not claimed to validate
water-process physics. A real water-system policy needs domain-specific validation.

Authentication, per-message MAC and replay checks run first, followed by mandatory
input/timing checks. A session/run change clears GRU and feature history before
inference. Each source has its own bounded T-1 buffer; the candidate is appended
only after health, policy, additional checks and on-time scheduling accept it.
The model assesses prior context plus the current authenticated candidate without
committing it first. No rejected/anomalous/deferred/late candidate enters accepted
history. Reauthentication requires recommissioning; expired/revoked sessions
cannot use retained context because authentication stops them first.

Cold startup is deliberately fail-closed. It cannot acquire T-1 accepted readings
while requiring T observations to approve the first reading. The explicit
administrative `commission_trusted_history` API therefore loads independently
trusted historical context, bound to source, session and recording. It is not a
network-message endpoint and does not advance replay counters or declare those
observations pipeline-accepted. Production commissioning requires its own trusted
provenance; never feed arbitrary rejected network messages to this API.
The dashboard's clearly labelled demonstration uses the checksum-verified local
nominal recording and a new authenticated session, then submits a signed current
candidate through the complete backend. It never searches for a favorable prediction.

Insufficient/stale history, missing/corrupt artifacts, invalid features or model
exceptions return unknown evidence, never healthy. SKAB anomalous maps explicitly
to the existing policy category `anomalous_reading`; this does not mean faulty or
malicious. Missing evidence stays distinct from authentication/replay rejection,
ML anomaly, policy rejection and deadline failure in backend audit fields.

Artifact loading uses CPU `torch.load(weights_only=True)`, strict state keys,
metadata/schema validation and a checksum. Checksums detect accidental changes,
not an attacker able to replace both metadata and weights: model deployment must
remain a trusted administrative operation. The model is loaded once, uses eval
and inference mode, and never fits transformations while processing messages.

## Timing and limitations

CPU inference includes preprocessing/tensor conversion and is also measured as
network-only execution. Benchmarks use batch one, 20 warm-ups and 200 measured
iterations, reporting median/p95/mean/max, with two Torch CPU threads. Hardware:
Intel i5-10300H, four cores/eight logical processors, NVIDIA GTX 1650 4GB,
Windows 11, Python 3.12.6. Training uses CUDA if available; inference supports CPU.

Message MAC and source handshake timings remain the receiver's measured counters.
The backend separately reports total application wall time. EDF overhead remains
simulation units; measured milliseconds are never silently added to those units.
No calibrated unit conversion or formal real-time guarantee exists. If a physical
deadline budget is smaller than measured end-to-end p95, the deployment would be
infeasible without a smaller model, scheduling changes or faster hardware.

20 observations require 19 prior observations (normally 19–38 seconds of history);
64 require 63 (normally 63–126 seconds). With commissioned context, each new
candidate can be assessed immediately, without waiting for future observations.
Numeric history memory is (T-1)*8*8 bytes per source plus timestamps/Python overhead.
Long gaps require trusted recommissioning. The accepted-only runtime context can
diverge from offline recordings after rejections; offline test metrics do not
establish closed-loop runtime accuracy. All experiments come from one water rig,
not the vehicle simulator, and correlated overlapping windows inflate apparent
sample counts. No claim of vehicle accuracy or autonomous safety certification is made.

## Reproduction

```powershell
# Existing .venv; CUDA build selected for the detected GPU/driver
.\.venv\Scripts\python.exe -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu126
# CPU-only alternative: same version, --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m src.ml.skab_dataset acquire
.\.venv\Scripts\python.exe -m src.ml.skab_dataset prepare
.\.venv\Scripts\python.exe -m src.ml.train_gru_sensor_model --epochs 30 --batch-size 256 --lr 0.001 --seed 42
.\.venv\Scripts\python.exe -m src.ml.evaluate_gru_sensor_model
.\.venv\Scripts\python.exe -m src.ml.cross_validate_gru
.\.venv\Scripts\python.exe -m src.ml.benchmark_gru_pipeline
.\.venv\Scripts\python.exe -m src.ml.report_gru_results
.\.venv\Scripts\python.exe -m src.ml.replay_skab_gru
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

Archive the prior result directory deliberately before reproducing evaluation;
never change hyperparameters using held-out results. GPU and CPU inference builds
may differ slightly numerically. The artifact contains the complete feature order,
scaler, class mapping, domain, architecture, threshold, window length, dataset
commit, split hashes, seed and training history. Original raw data is unnecessary
for ordinary model loading and authenticated inference.
