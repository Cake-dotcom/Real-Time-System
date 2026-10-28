# Command reference and verification status

Run commands from the repository root after environment activation. E = executed during this documentation task; S = source/CLI verified; P = prior successful execution recorded in cleanup evidence. S/P is not a claim of a new clean installation. No training or expensive benchmark was run for these documents.

| Command | Inputs -> outputs | Status / common failure |
|---|---|---|
| python -m venv .venv | Python 3.12 -> local environment | S; Python missing: install/select interpreter |
| .\.venv\Scripts\Activate.ps1 | Existing Windows env -> active shell | S; restricted activation: invoke env Python directly |
| python -m pip install --upgrade pip | Network/package index -> installer update | S; network/proxy errors need environment repair |
| python -m pip install -r requirements.txt | Pinned manifest -> installed dependencies | S/P; no fresh install here; use compatible Python/platform |
| python -m pip check | Installed env -> consistency report | P; fix version mismatch, do not alter gates |
| python -m streamlit run src/dashboard/app.py | Models + CSV + environment -> local dashboard | S/P; root/port/import errors: correct path/env/port |
| python -m pytest -q --tb=short | Tests + assets + dependencies -> test summary | S/P; last saved 278 passed; no new full run here |
| python -m compileall -q src tests | Python sources -> bytecode/syntax result | S; creates caches; documentation instead parses AST |
| python -m src.ml.validate_sensor_dataset | Vehicle CSV -> schema/count validation | S; restore expected CSV/working directory |
| python -m src.ml.train_sensor_model | Vehicle CSV -> RF artifact/report | S; overwrites model/report; use separate checkout |
| python -m src.ml.evaluate_sensor_model --all-runs --output-dir results/local_rf_evaluation | Vehicle data/artifact -> grouped evaluation JSON | S; preserve artifacts; missing feature/dependency failures |
| python -m src.ml.skab_dataset acquire | Pinned manifest + network -> original SKAB files | S; refuses mismatched originals; optional when included |
| python -m src.ml.skab_dataset prepare | Original SKAB -> arrays/splits/scaler reports | S; schema/hash/gap failures must be investigated |
| python -m src.ml.train_gru_sensor_model --epochs 30 --batch-size 256 --lr 0.001 --seed 42 | Prepared SKAB -> candidates, final model/history | S; expensive and writes fixed paths; preserve originals |
| python -m src.ml.evaluate_gru_sensor_model | Fixed artifacts/prepared test -> held-out report | S; refuses existing test report; separate checkout |
| python -m src.ml.cross_validate_gru | Prepared training groups -> outer group diagnostics | S; expensive; fixed outputs must be preserved |
| python -m src.ml.benchmark_gru_pipeline | GRU/context -> latency JSON | S; fixed output; not necessary to start app |
| python -m src.security.security_system | Included login model -> risk/action/schedule example | S; needs joblib/sklearn; separate from sensor pipeline |
| python -m src.scheduler.experiments --full --workers 4 --output results/local_scheduling | Seeded synthetic configs -> raw/aggregate JSON and traces | S; use new directory; not actual authentication |
| python scripts/evaluate_laboratory.py --output results/local_laboratory | Assets/presets -> authenticated JSON/CSV/report | S/P for canonical prior run; choose fresh output |
| python scripts/report_optimization.py | Preserved baseline/final traces -> audited comparison reports | S/P; rewrites derived reports, so preserve evidence |
| python scripts/benchmark_optimization.py baseline --workers 4 --seeds 20 | Current source + generator -> baseline archive/traces | S/P; refuses existing stage directory |
| python scripts/benchmark_optimization.py optimized --workers 4 --seeds 20 | Same configs -> optimized archive/traces | S/P; existing results must be preserved |
| python scripts/evaluate_optimized_laboratory.py | Presets/artifacts -> 44-run evidence/profiles | S/P; fixed output directory, preserve originals |
| python -m src.ml.benchmark_source_auth --messages 1000 --repetitions 10 --output results/local_source_auth.json | Synthetic signed traffic -> timing JSON | S; measured desktop latency, not WCET |
| python docs/documentation_sources/verify_documentation.py | Source/evidence/docs -> validation JSON + illustrative trace | E; standard library; no application dependencies |

The small scheduler example printed in the README and Chapter 11 is executed by the last command. Gate policies and exact registry names are checked from source. The full suite and dashboard startup were previously executed successfully and retained under results/repository_cleanup; those historical logs remain unchanged.
