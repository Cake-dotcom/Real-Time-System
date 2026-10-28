"""Evaluate locked artifacts once; no fitting/threshold changes on held-out test."""
import json
import platform
import time
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import precision_recall_curve
from src.ml.gru_sensor_model import ARTIFACT, GRUPredictor
from src.ml.train_gru_sensor_model import RESULTS, load_split, metrics, scores_for
from src.ml.skab_dataset import ROOT, PROCESSED, digest, write_json


def benchmark(call, warmup=20, repetitions=200):
    for _ in range(warmup):
        call()
    timings = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        call()
        timings.append((time.perf_counter_ns() - start) / 1e6)
    return {"median_ms": float(np.median(timings)), "p95_ms": float(np.percentile(timings, 95)),
            "mean_ms": float(np.mean(timings)), "max_ms": float(max(timings)),
            "warmup": warmup, "repetitions": repetitions, "batch_size": 1}


def main():
    target = RESULTS / "test_evaluation.json"
    if target.exists():
        raise FileExistsError("Test report exists; inspect it instead of repeatedly tuning against test")
    torch.set_num_threads(2)
    predictor = GRUPredictor()
    meta = predictor.metadata
    selection = json.loads((RESULTS / "selection.json").read_text())
    for split, expected in meta["split_hashes"].items():
        if digest((PROCESSED / f"{split}.json").read_bytes()) != expected:
            raise ValueError("Split changed since training")
    x, y, groups, ends = load_split("test")
    x = x[:, -predictor.length:].copy()
    gs = scores_for(predictor.model, x, "cpu")
    rfpath = ROOT / "models/skab_random_forest.joblib"
    forest = joblib.load(rfpath)
    rs = forest.predict_proba(x[:, -1])[:, 1]
    thresholds = {"GRU": meta["threshold"], "RF_refit_SKAB": selection["rf"]["threshold"]}
    results = {}
    for name, scores in [("GRU", gs), ("RF_refit_SKAB", rs)]:
        results[name] = metrics(y, scores, thresholds[name])
        results[name]["per_group"] = {g: metrics(y[groups == g], scores[groups == g], thresholds[name]) for g in np.unique(groups)}
        precision, recall, ts = precision_recall_curve(y, scores)
        write_json(RESULTS / f"{name}_precision_recall.json", {"precision": precision.tolist(),
                   "recall": recall.tolist(), "thresholds": ts.tolist()})
    raw = x[0].astype(np.float64) * predictor.scale + predictor.mean
    results["GRU"]["cpu_inference"] = benchmark(lambda: predictor.predict(raw))
    tensor = torch.from_numpy(x[:1])
    with torch.inference_mode():
        results["GRU"]["cpu_network_only"] = benchmark(lambda: predictor.model(tensor))
    forest.set_params(n_jobs=1)
    results["RF_refit_SKAB"]["cpu_inference"] = benchmark(lambda: forest.predict_proba(x[:1, -1]))
    results["GRU"]["artifact_bytes"] = ARTIFACT.stat().st_size + ARTIFACT.with_suffix(".json").stat().st_size
    results["RF_refit_SKAB"]["artifact_bytes"] = rfpath.stat().st_size
    pd.DataFrame({"group": groups, "end_row": ends, "label": y, "gru_score": gs,
                  "rf_score": rs, "gru_prediction": gs >= thresholds["GRU"],
                  "rf_prediction": rs >= thresholds["RF_refit_SKAB"]}).to_csv(RESULTS / "test_predictions.csv", index=False)
    report = {"models": results, "test_windows": len(y), "test_groups": len(np.unique(groups)),
              "test_class_counts": np.bincount(y).tolist(), "synthetic_examples": 0,
              "hardware": {"cpu": "Intel Core i5-10300H (4 cores / 8 threads)",
                           "gpu": "NVIDIA GeForce GTX 1650 4GB", "platform": platform.platform(),
                           "python": platform.python_version(), "torch": str(torch.__version__),
                           "inference_device": "cpu", "torch_threads": torch.get_num_threads()},
              "gru_training_seconds": meta["training_seconds"],
              "rf_training_seconds": selection["rf"]["training_seconds"],
              "limitations": ["Original vehicle RF cannot consume SKAB; refitted same classifier settings.",
                              "No faulty class or malicious-attack attribution supported.",
                              "Five held-out components on one rig, correlated windows.",
                              "Inference latency is measured wall time, not calibrated EDF cost."]}
    write_json(target, report)
    lines = ["# Locked SKAB test results", "", "| Model | Accuracy | Macro F1 | Anomaly recall | FPR | FNR | CPU median ms | CPU p95 ms |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in results.items():
        lines.append(f"| {name} | {row['accuracy']:.4f} | {row['macro_f1']:.4f} | {row['classification_report']['anomalous']['recall']:.4f} | {row['false_positive_rate']:.4f} | {row['false_negative_rate']:.4f} | {row['cpu_inference']['median_ms']:.3f} | {row['cpu_inference']['p95_ms']:.3f} |")
    (RESULTS / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
