# Repository cleanup verification

Cleanup completed on 2026-10-29. **The project is below the 5 GB target**, with
required source, models, data and research evidence retained. No scheduling,
security, authentication, ML or experimental parameters were changed.

## Size accounting

Sizes below are logical file bytes, rounded to decimal MB/GB. They are not NTFS
allocated-space measurements. Exact inventory values are saved in
[before.json](../results/repository_cleanup/before.json) and
[after.json](../results/repository_cleanup/after.json).

| Measurement | Size |
|---|---:|
| Initial project, including local environment and `.git` | 6,005,699,112 bytes (6.006 GB) |
| Final project, including `.git` | approximately 306 MB (0.306 GB) |
| Currently tracked working files | approximately 62.27 MB |
| All intended commit files: tracked + untracked, honoring final ignores | approximately 233.2 MB |
| Existing `.git` directory | approximately 72.91 MB |
| Existing HEAD checkout + current Git directory, conservative clone estimate | approximately 135.17 MB |
| Prepared-project checkout + existing Git directory + uncompressed new objects, conservative estimate | approximately 539.4 MB |

The audit's first automated before measurement is 6,005,704,340 bytes because it
includes the newly created audit script; the initial measurement above precedes
that script. A prepared-project clone has not been made or published. Its estimate
deliberately counts another uncompressed copy of every intended file as possible
new Git objects; actual packing/sharing generally reduces that. A clone of the
current HEAD alone omits existing uncommitted/untracked work and is not the full
prepared project. [git_history.json](../results/repository_cleanup/git_history.json)
records that distinction.

Git metadata grew between measurements while this task was active; no cleanup
command committed, repacked, garbage-collected or rewrote history. All size
estimates use the observed final metadata instead of assuming it stayed constant.
No intended file exceeds the audit's 100 MiB threshold. The largest retained file
is `models/skab_random_forest.joblib`, 62,893,385 bytes. No LFS migration or external
artifact hosting was needed.

## Removed and excluded

- Project `.venv/`: initially 5,716,728,044 bytes. It was temporarily relocated,
  verified and used for post-cleanup tests, then discarded. An interrupted move
  encountered locked files; remaining duplicate files were hash-checked before
  their source copies were removed. No application source was relocated.
- Seven cache directories: generated Python bytecode under source/tests and the
  pytest cache. Exact paths/bytes are in
  [removed_caches_and_duplicate_logs.json](../results/repository_cleanup/removed_caches_and_duplicate_logs.json).
- Root `baseline_tests.log` and `optimization_tests.log`: removed only after their
  SHA-256 hashes matched the retained canonical logs under `results/optimization/`.

The final `.gitignore` excludes local virtual environments, Python/tool/test
caches, coverage outputs, editor/OS state, `.env` secrets, Streamlit secrets and
specific root scratch logs. It **no longer ignores required GRU weights, SKAB RF
weights, raw SKAB data or prepared arrays**. All data/model/research-result files
remain eligible for the prepared commit. No tracked generated files required
untracking, and the Git index was not changed by cleanup commands.

Deleting the environment removes installed dependencies, not functionality.
Before the next application run, create a new environment and install the root
requirements as documented in the README. That installation may again exceed
5 GB locally, especially with CUDA libraries; it is excluded from Git. No fresh
network installation or cross-platform dependency resolution was tested here.

## Retained assets

| Directory | Approximate size | Why retained |
|---|---:|---|
| `models/` | 119.60 MB | All five artifacts: vehicle RF, legacy login model, GRU weights/metadata and SKAB RF comparison |
| `results/` | 101.1 MB | Research metrics, source snapshots, full traces, profiles and verification; historical duplicates intentionally kept |
| `data/` | 11.99 MB | Vehicle/login CSVs, SKAB originals/license, processed arrays, split/scaler/source manifests |
| `.git/` | 72.91 MB | Existing history and metadata, preserved without rewriting |

Other large retained files include the login model (41,307,367 bytes), vehicle RF
(15,373,324 bytes), scheduling workload evidence (15,048,775 bytes), and original
optimization trace archive (11,474,712 bytes). Raw/processed SKAB manifest copies
and repeated historical plots remain because they belong to documented stages.
No in-place compression changed application paths or formats.

## Verification

- **278 tests passed in 57.09 seconds**, zero failures. Command: `python -B -m
  pytest -q --tb=short -p no:cacheprovider`, using the existing documented Python
  3.12.6 environment temporarily outside the project. Bytecode generation was
  disabled. [Full output](../results/repository_cleanup/tests.log).
- Syntax parsing passed for **71 Python files**. README local links all resolve.
- Saved vehicle RF and GRU loaded and produced normal predictions on smoke inputs;
  GRU verified its weight checksum and prepared test windows loaded successfully.
- All **eight** laboratory scheduler modes ran on the same seeded workload with
  security compliance and on-time completion invariants checked.
- Actual authenticated original/optimized laboratory comparison used the same
  workload and both completed all four verified messages.
- Streamlit started on localhost and returned **HTTP 200** from its health
  endpoint. Full app execution/UI correspondence is separately covered by the
  pytest AppTest tests. The verification server was stopped afterward.
- `pip check` before relocation reported no broken requirements. It also warned
  about an existing orphaned pip distribution in the local environment; that
  environment was subsequently discarded, not committed.
- Before/after SHA-256 audit reports **no changes to any existing protected file**:
  application code, tests, existing scripts/docs, datasets, model artifacts and
  experimental results. Existing requirements were not edited. Git diff checks
  pass; unrelated pre-existing modifications remain untouched.

Detailed smoke output is in [smoke.json](../results/repository_cleanup/smoke.json).
The new audits write only cleanup evidence; they do not rerun scripts that would
overwrite historical experiment results.

## README and publication notes

The rewritten README covers overview/motivation, architecture, implemented
schedulers, timing concepts, security flow, RF/GRU domain boundaries, repository
structure, prerequisites/setup, dashboard use, tests, training/evaluation,
experiments, datasets/artifacts, configuration, metrics, limitations, prototype
security and license status. Commands use relative project paths and do not expose
credentials or private machine paths.

The bounded candidate-file credential scan found no matches for the checked
private-key/token patterns. Demo authentication keys remain intentional fixtures;
this heuristic is not an exhaustive secret audit. Existing historical documents
and profiling records contain local-path metadata, listed in `after.json` under
`personal_path_files`. Review these before public publication if sensitive; their
research bytes were intentionally preserved instead of silently rewritten.

There is **no root project license**. No license was invented. SKAB's upstream
license and attribution remain in the dataset tree; review applicable rights
before redistribution. These are publication considerations, not size blockers.

No commit or push was performed. Review and include the existing untracked work
and newly unignored required artifacts when preparing the GitHub commit. The
intended-file inventory is explicit in `after.json`. No size blocker remains.

## Files changed by this cleanup

Modified: `README.md`, `.gitignore`.

Added: `docs/repository_cleanup_plan.md`, this report,
`scripts/audit_repository.py`, `scripts/verify_repository.py`, and
`results/repository_cleanup/` containing before/after inventories, README/ignore
backups, installed dependency inventory, removed-file manifest, test/smoke/startup
logs and Git-size evidence. Removed only the environment, recorded caches and two
verified duplicate root logs. All other Git status changes predate this cleanup.
