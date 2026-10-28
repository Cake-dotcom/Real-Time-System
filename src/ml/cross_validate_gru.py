"""Outer group robustness checks with the separate validation split for selection.

Each outer fold's labels are used only for scoring, never stopping/thresholding.
This does not modify the locked production artifact or inspect final test data.
"""
import json
import joblib
import numpy as np
import torch
from sklearn.base import clone
from sklearn.model_selection import GroupKFold
from src.ml.skab_dataset import PROCESSED, ROOT, write_json
from src.ml.train_gru_sensor_model import load_split, fit, metrics, scores_for, select_threshold, RESULTS


def main():
    torch.set_num_threads(2)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    config = json.loads((PROCESSED / "config.json").read_text())
    chosen = json.loads((RESULTS / "selection.json").read_text())["selected"]
    x, y, groups, _ = load_split("train")
    vx, vy, validation_groups, _ = load_split("validation")
    mapping = {g: i for i, component in enumerate(config["overlap_components"]) for g in component}
    ids = np.array([mapping[g] for g in groups])
    raw = x.astype(np.float64) * config["scale"] + config["mean"]
    external = vx.astype(np.float64) * config["scale"] + config["mean"]
    original = joblib.load(ROOT / "models/sensor_health_model.joblib")["model"].named_steps["classifier"]
    reports = []
    for fold, (tr, hold) in enumerate(GroupKFold(3).split(x, y, ids)):
        mean, scale = raw[tr].mean(axis=(0, 1)), raw[tr].std(axis=(0, 1))
        scale[scale == 0] = 1
        tx = ((raw[tr] - mean) / scale).astype(np.float32)
        validation = ((external - mean) / scale).astype(np.float32)
        hx = ((raw[hold] - mean) / scale).astype(np.float32)
        model, info = fit(tx, y[tr], validation, vy, hidden=chosen["architecture"]["hidden_size"],
                          length=chosen["window_length"], epochs=15, batch_size=chosen["batch_size"],
                          lr=chosen["lr"], seed=42 + fold, device=device)
        forest = clone(original).set_params(n_jobs=2).fit(tx[:, -1], y[tr])
        threshold = select_threshold(vy, forest.predict_proba(validation[:, -1])[:, 1])
        reports.append({"fold": fold, "fit_components": sorted(set(ids[tr].tolist())),
                        "held_out_components": sorted(set(ids[hold].tolist())),
                        "selection_groups": sorted(set(validation_groups.tolist())),
                        "selection_split": "original validation only; distinct from all outer train/holdout groups",
                        "gru": metrics(y[hold], scores_for(model, hx[:, -chosen['window_length']:].copy(), device), info["threshold"]),
                        "rf": metrics(y[hold], forest.predict_proba(hx[:, -1])[:, 1], threshold),
                        "best_epoch": info["best_epoch"]})
        write_json(RESULTS / "outer_group_evaluation.json", reports)


if __name__ == "__main__":
    main()
