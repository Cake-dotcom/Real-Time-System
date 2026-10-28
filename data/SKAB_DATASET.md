# SKAB dataset stage

This document records the completed dataset-stage protocol. The subsequent GRU
stage is implemented; see [current model documentation](../docs/gru_sensor_model.md).
The historical dataset-stage counts and verification below remain unchanged.

## Provenance and selection

Selected **Skoltech Anomaly Benchmark (SKAB), v0.9**, from the authors' repository:
https://github.com/waico/SKAB . Downloaded and inspected on 2026-10-27 at pinned
commit `b2c0d46c2971dcbfe71e26087b6d231998bb91c2`.
All 35 CSVs and three documentation/license files were obtained directly from
`raw.githubusercontent.com/waico/SKAB/<commit>/`, without credentials.
The 38 originals total 4,440,904 bytes. Exact URLs, byte lengths and SHA-256
checksums for every original are in [source_manifest.json](skab/source_manifest.json).
Acquisition refuses to replace altered originals or accept a changed locked download.
The repository declares GPL-3.0; its complete LICENSE is preserved locally.
No separate data-specific license was found in the downloaded documentation.
Retain the attribution and license when sharing under the applicable terms;
this project does not relicense the dataset. Raw and processed data are Git-ignored.

Use the citation supplied by the authors: Iurii D. Katser and Vyacheslav O.
Kozitsin (2020), *Skoltech Anomaly Benchmark (SKAB)*, Kaggle,
DOI https://doi.org/10.34740/KAGGLE/DSV/1693952 . The repository's position paper
is described as submitted; no unverified publication details are claimed here.

The official README's **Datasets** section describes measurements and annotations;
the official `data/README.md` describes the physical experiments. The benchmark
uses a water-circulation testbed with controlled disturbances, including valve
closures and other deliberately introduced operating anomalies. These are recorded
physical experiments, not naturally occurring field failures or authenticated
vehicle attacks. **No synthetic augmentation was generated in this project.**

Alternatives researched from their official sources:

| Candidate | Availability and temporal/label evidence | Decision |
|---|---|---|
| NASA SMAP/MSL | [Telemanom README](https://github.com/khundman/telemanom), Getting Started and Raw experiment data: real spacecraft sequences, anomaly intervals, anonymized time/channel names, telemetry plus encoded commands. Current instructions require a Kaggle API key. Repository declares Apache-2.0; a separate dataset license was not independently verified. Published values already use test-set min/max scaling. | Useful benchmark, but less suitable for a fresh leakage-controlled scaler and named physical features. Not downloaded. |
| SWaT | [Official characteristics](https://www.sutd.edu.sg/itrust/itrust-labs/datasets/dataset-characteristics/swat/): original release has 51 sensor/actuator streams over normal and attack periods, with labels. | Strong security dataset, but gated access. Not downloaded. |
| WADI | [Official characteristics](https://www.sutd.edu.sg/itrust/itrust-labs/datasets/dataset-characteristics/wadi/): original release has 123 sensor/actuator streams; updated attack CSV labels attack as -1 and normal as 1. | Strong multivariate alternative, also gated. Not downloaded. |

SWaT/WADI [request form](https://www.sutd.edu.sg/itrust/request-for-datasets/)
requires name, organisation, institutional email and consent; requests may take
three working days. [Usage terms](https://www.sutd.edu.sg/itrust/itrust-labs/datasets/terms-of-usage/)
require attribution, publication notification, publication of requester details,
and prohibit sharing the supplied datasets. No request was submitted on the user's behalf.
SKAB was selected for immediate reproducible access, explicit sensor names,
recorded anomalies and experiment-level evaluation. Access convenience does not
make it representative of the vehicle domain.

## Actual schema and mapping

CSV separator is semicolon. All files contain `datetime` and these eight numeric
features in this fixed order (no categorical feature encoding is needed):

| Feature | Physical quantity / unit |
|---|---|
| Accelerometer1RMS | Vibration acceleration, g |
| Accelerometer2RMS | Vibration acceleration, g |
| Current | Motor current, A |
| Pressure | Loop pressure after pump, bar |
| Temperature | Motor body temperature, degrees C |
| Thermocouple | Fluid temperature, degrees C |
| Voltage | Motor voltage, V |
| Volume Flow RateRMS | Fluid flow, litre/minute |

The actual last column name differs from the README's `RateRMS`; the loader uses
the original CSV name. The file listing also differs from the README's numbering:
actual valve1 files are 0..15 and valve2 files 0..3. The pinned inventory is authoritative.

The 34 disturbance recordings have binary `anomaly` and `changepoint` columns.
`anomaly=0` maps to **normal**, `anomaly=1` to **anomalous**. Changepoints are
validated and preserved in raw data but excluded from model features and targets.
The nominal-only CSV has neither label column; its all-normal mapping comes from
the authors' explicit description of `anomaly-free/anomaly-free.csv`.
There is **no supported separate faulty class**, no per-sensor health attribution,
and no ground truth for MAC verification, replay, criticality or scheduling risk.
Physical process anomalies do not necessarily mean faulty sensors.

These eight measurements must not be forced into the existing distance-based RF
feature schema. Existing `sensor_health` still loads the same RF bundle and passes
its predictions through the existing risk/validation/scheduling logic. This module
is an offline research data interface only; it is not invoked by the dashboard.

## Validation, overlap and splits

Actual totals: **46,806 source rows**, **33,739 normal**, **13,067 anomalous**
(27.92% anomalous). No missing/nonfinite feature values were accepted. Schema,
binary labels, timestamps and strict chronological order are validated; malformed
records raise errors rather than being imputed or reordered. Numeric values are
not clipped against invented physical limits.

The 35 files contain **1,290 repeated timestamp-plus-measurement samples**, leaving
45,516 unique such samples. Shared samples connect them into **30 components**.
They are grouping units, not proof of statistical independence: all use one rig.
The overlap sets are:

- anomaly-free/anomaly-free.csv and other/5.csv;
- other/2.csv, other/3.csv and other/4.csv;
- other/10.csv and other/11.csv;
- other/12.csv and other/13.csv.

There are **235 unique samples with conflicting duplicate labels**, occurring in
470 rows. Original annotations remain unchanged. These rows cannot be targets;
57 otherwise eligible windows are excluded. Their measured values may remain
historical context. All overlapping components happen to be assigned to training;
validation/test contain no duplicated source samples or ambiguous target labels.
Duplicates with consistent labels remain within their split and affect weighting.

Deterministic NumPy seed 42 assigns whole components within experiment families.
For each non-nominal family, floor(20% of components), at least one, goes to each
held-out split; the remainder trains. The component containing the long nominal
recording is training-only. Thus exact row percentages are not 60/20/20.
This is a held-out-experiment evaluation, not a globally chronological deployment
forecast; chronology is maintained inside recordings. No window crosses a file
or component boundary, and overlapping files cannot cross splits.

| Split | Files | Components | Rows | Normal rows | Anomalous rows | Windows | Normal targets | Anomalous targets |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Train | 25 | 20 | 36,160 | 26,782 | 9,378 | 33,623 | 24,858 | 8,765 |
| Validation | 5 | 5 | 5,178 | 3,388 | 1,790 | 4,863 | 3,073 | 1,790 |
| Test | 5 | 5 | 5,468 | 3,569 | 1,899 | 5,153 | 3,254 | 1,899 |

Fit per-feature mean/population standard deviation on **training rows only**;
constant-feature scale becomes 1. No test/validation fitting, interpolation,
centered smoothing, or future observations are used. Ambiguous labels do not
affect this unsupervised scaler. Scaled arrays are float32; timestamps, original
binary labels, valid-target masks and window endpoints are also stored.

Windows contain 64 observations, stride 1, with the original endpoint label.
Observed steps: 44,222 one-second steps, 2,479 two-second steps and 70 larger gaps
(up to 247 seconds). Windows allow 1/2-second steps and break at larger gaps.
They are **not fixed-duration 64-second windows**. Timestamps accompany every
window; no resampling is performed. Within-split windows overlap, so their count
must not be treated as independent statistical sample size.

## Reproduction and future interface

From the project root with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m src.ml.skab_dataset acquire
.\.venv\Scripts\python.exe -m src.ml.skab_dataset prepare
.\.venv\Scripts\python.exe -m pytest -q
```

`acquire` needs internet; `prepare` and window iteration are offline. Dependencies
are already pinned in requirements.txt; inspected runtime used NumPy 2.5.3 and
pandas 3.0.6. The saved config records feature order, seed, window parameters,
label policy, component membership and fitted scaling statistics.

```python
from src.ml.skab_dataset import iter_windows
for x, y, provenance in iter_windows(split="train"):
    # x: float32[64, 8]; y: 0/1; provenance includes all window timestamps
    pass
```

The loader checks processed checksums, feature configuration, grouping, eligibility
and sequence structure. Missing files or invalid evidence raise errors. It never
silently falls back to another dataset. No model is trained by acquisition or preparation.
For the GRU stage, batch these windows as [batch,64,8], tune only on validation,
and reserve test for final evaluation. Report per-component precision/recall/F1,
PR-AUC and false alarms, with temporal uncertainty; account for irregular timing
and repeated training samples. A binary offline model will require a separately
reviewed domain/interface adaptation before production use. Do not interpret
anomaly probabilities as authentication evidence or a new faulty class.

## Files produced by this stage

- Modified `.gitignore` (exclude raw SKAB); README.md (entry point).
- Added this document, `src/ml/skab_dataset.py`, `tests/test_skab_dataset.py`.
- Added `data/skab/source_manifest.json`, `config.json`, `train.json`,
  `validation.json`, `test.json`, `validation_report.json`, `verification.json`.
- Downloaded `data/raw/skab/{README.md,LICENSE,data/README.md}` and all 35 CSVs
  under `data/{anomaly-free,other,valve1,valve2}`. Every path is enumerated in
  source_manifest.json.
- Generated `data/processed/skab/`: 35 recording `.npz` files (every filename is
  enumerated in the three split manifests), plus config.json, train.json,
  validation.json and test.json. No original file is modified.

The detailed per-record counts, gaps, conflicts, split assignment and runtime
versions are in [validation_report.json](skab/validation_report.json).
Regression and real-data reproducibility results are in
[verification.json](skab/verification.json). Model replacement is deferred.

Final verification: **118 tests passed in 62.13 seconds**, comprising the original
99 tests and 19 dataset tests. Tests cover schema/labels, malformed and missing
records, chronological window boundaries, overlap components, ambiguous-label
exclusion, training-only scaling under extreme held-out values, deterministic
preparation, checksum tampering and manifest leakage. The initial sandbox run
could not create pytest temporary directories; the complete suite passed outside
the sandbox. Two actual-data preparation passes produced identical output bytes,
and the loader successfully iterated all 43,639 final windows. `git diff --check`
passed. verification.json enumerates every one of the 89 stage files, including
downloaded originals and generated artifacts.

The RF artifact SHA-256 remains
`cd30ba07f4e04ae50585e5fc7e7662ad4ce78de1df5c70fa1400ef4ee60768d1`;
the baseline sensor CSV remains
`c7d25ffe83d4a74d28a1f1e8d21cc2b5b8938d8c8dece663130781f1a903a0b5`.
Remaining research limitations are single-rig domain bias, irregular timing,
correlated/duplicated training observations and ambiguous source annotations;
these are documented and not evidence of vehicle-domain accuracy.
