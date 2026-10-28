"""Validation-only selection; locked held-out evaluation in a separate command."""
import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import argparse
import copy
import json
import random
import time
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.base import clone
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, average_precision_score, roc_auc_score,
                             precision_recall_curve, auc)
from sklearn.model_selection import GroupKFold
from torch.utils.data import DataLoader, TensorDataset

from src.ml.gru_sensor_model import ARTIFACT, FEATURES, GRUClassifier, save_artifact
from src.ml.skab_dataset import PROCESSED, ROOT, iter_windows, write_json, digest

RESULTS = ROOT / "results/gru"


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False


def load_split(split):
    samples = list(iter_windows(split=split))
    if not samples:
        raise ValueError("Empty split")
    x = np.stack([s[0] for s in samples])
    y = np.array([s[1] for s in samples], dtype=np.int64)
    groups = np.array([s[2]["group"] for s in samples])
    ends = np.array([s[2]["end_row"] for s in samples])
    if not np.isfinite(x).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Invalid training data")
    return x, y, groups, ends


def metrics(y, score, threshold):
    pred = score >= threshold
    cm = confusion_matrix(y, pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    precision, recall, thresholds = precision_recall_curve(y, score)
    return {"accuracy": accuracy_score(y, pred), "macro_f1": f1_score(y, pred, average="macro"),
            "weighted_f1": f1_score(y, pred, average="weighted"),
            "classification_report": classification_report(y, pred, labels=[0, 1],
                 target_names=["normal", "anomalous"], output_dict=True, zero_division=0),
            "confusion_matrix": cm.tolist(), "false_positive_rate": float(fp / (fp + tn)) if fp + tn else None,
            "false_negative_rate": float(fn / (fn + tp)) if fn + tp else None,
            "average_precision": float(average_precision_score(y, score)) if len(np.unique(y)) == 2 else None,
            "pr_auc_trapezoidal": float(auc(recall, precision)),
            "roc_auc": float(roc_auc_score(y, score)) if len(np.unique(y)) == 2 else None,
            "threshold": float(threshold)}


def select_threshold(y, scores):
    candidates = np.linspace(0.05, 0.95, 91)
    values = [f1_score(y, scores >= t, average="macro") for t in candidates]
    return float(candidates[int(np.argmax(values))])


def scores_for(model, x, device, batch_size=512):
    model.eval()
    result = []
    with torch.inference_mode():
        for offset in range(0, len(x), batch_size):
            logits = model(torch.from_numpy(x[offset:offset + batch_size]).to(device))
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite model output")
            result.extend(logits.softmax(-1)[:, 1].cpu().numpy())
    return np.asarray(result)


def fit(x, y, vx, vy, *, hidden=64, length=64, epochs=30, patience=5,
        batch_size=256, lr=0.001, seed=42, device="cpu", log_path=None):
    if (x.ndim != 3 or vx.ndim != 3 or x.shape[-1] != 8 or vx.shape[-1] != 8
            or len(x) != len(y) or len(vx) != len(vy)
            or not 1 <= length <= min(x.shape[1], vx.shape[1])
            or not 1 <= hidden <= 256 or epochs < 1 or patience < 1
            or batch_size < 1 or not np.isfinite(lr) or lr <= 0):
        raise ValueError("Invalid training shapes or hyperparameters")
    if not len(x) or not len(vx) or set(np.unique(y)) != {0, 1} or set(np.unique(vy)) != {0, 1}:
        raise ValueError("Training requires nonempty splits and both classes")
    if not np.isfinite(x).all() or not np.isfinite(vx).all() or not np.isin(vy, [0, 1]).all():
        raise ValueError("Invalid features or targets")
    seed_all(seed)
    architecture = {"input_size": 8, "hidden_size": hidden, "layers": 1, "dropout": 0.2}
    model = GRUClassifier(**architecture).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.0001)
    counts = np.bincount(y, minlength=2)
    weights = torch.tensor(len(y) / (2 * counts), dtype=torch.float32, device=device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    loader = DataLoader(TensorDataset(torch.from_numpy(x[:, -length:].copy()), torch.from_numpy(y)),
                        batch_size=batch_size, shuffle=True, num_workers=0)
    best, history, stalled = -1, [], 0
    started = time.perf_counter()
    for epoch in range(epochs):
        model.train()
        losses = []
        for xb, yb in loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb.to(device))
            loss = loss_fn(logits, yb.to(device))
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        scores = scores_for(model, vx[:, -length:].copy(), device)
        threshold = select_threshold(vy, scores)
        score = f1_score(vy, scores >= threshold, average="macro")
        val_loss = float(np.mean(-(vy * np.log(np.clip(scores, 1e-7, 1))
                                  + (1 - vy) * np.log(np.clip(1 - scores, 1e-7, 1)))))
        history.append({"epoch": epoch + 1, "train_weighted_loss": float(np.mean(losses)),
                        "validation_unweighted_loss": val_loss, "validation_macro_f1": score,
                        "validation_anomaly_recall": float(((scores >= threshold) & (vy == 1)).sum() / (vy == 1).sum()),
                        "threshold": threshold})
        if score > best + 1e-5:
            best, best_epoch, best_threshold = score, epoch + 1, threshold
            state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stalled = 0
        else:
            stalled += 1
        if log_path:
            write_json(log_path, history)
        print(f"h={hidden} T={length} epoch={epoch+1} val_macro_f1={score:.4f}", flush=True)
        if stalled >= patience:
            break
    model.load_state_dict(state)
    return model, {"architecture": architecture, "window_length": length, "seed": seed,
                   "epochs_limit": epochs, "best_epoch": best_epoch, "patience": patience,
                   "batch_size": batch_size, "lr": lr, "weight_decay": 0.0001,
                   "class_weights": weights.cpu().tolist(), "threshold": best_threshold,
                   "validation_macro_f1": best, "history": history,
                   "training_seconds": time.perf_counter() - started}


def train(args):
    RESULTS.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    config = json.loads((PROCESSED / "config.json").read_text())
    x, y, groups, _ = load_split("train")
    vx, vy, _, _ = load_split("validation")
    # Locked before looking at test outcomes. Same endpoint population for every candidate.
    candidates = [(32, 20), (64, 20), (64, 64)]
    runs, best = [], -1
    for hidden, length in candidates:
        model, details = fit(x, y, vx, vy, hidden=hidden, length=length, epochs=args.epochs,
                             batch_size=args.batch_size, lr=args.lr, seed=args.seed, device=device,
                             log_path=RESULTS / f"history_h{hidden}_t{length}.json")
        runs.append(details)
        if details["validation_macro_f1"] > best:
            best = details["validation_macro_f1"]
            chosen = details
            selected_state = copy.deepcopy(model.cpu().state_dict())
    selected = GRUClassifier(**chosen["architecture"])
    selected.load_state_dict(selected_state)
    metadata = {**chosen, "format_version": 1, "features": FEATURES, "classes": ["normal", "anomalous"],
                "domain": "SKAB water circulation testbed", "mean": config["mean"], "scale": config["scale"],
                "dataset_commit": config["commit"], "preprocessing": config,
                "torch_version": str(torch.__version__), "training_device": device,
                "split_hashes": {s: digest((PROCESSED / f"{s}.json").read_bytes()) for s in ["train", "validation", "test"]}}
    save_artifact(ARTIFACT, selected, metadata)
    # Retain original artifact; clone the original RF classifier settings onto SKAB endpoint features.
    original = joblib.load(ROOT / "models/sensor_health_model.joblib")
    forest = clone(original["model"].named_steps["classifier"]).set_params(n_jobs=2)
    started = time.perf_counter()
    forest.fit(x[:, -1], y)
    rf_time = time.perf_counter() - started
    rf_score = forest.predict_proba(vx[:, -1])[:, 1]
    rf_threshold = select_threshold(vy, rf_score)
    joblib.dump(forest, ROOT / "models/skab_random_forest.joblib")
    summary = {"candidates": runs, "selected": chosen, "training_device": device,
               "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
               "rf": {"training_seconds": rf_time, "threshold": rf_threshold,
                       "validation": metrics(vy, rf_score, rf_threshold)},
               "original_rf_sha256": digest((ROOT / "models/sensor_health_model.joblib").read_bytes()),
               "test_used_for_selection": False}
    write_json(RESULTS / "selection.json", summary)
    # Group CV is a robustness diagnostic on TRAINING components only, never test tuning.
    mapping = {g: i for i, component in enumerate(config["overlap_components"]) for g in component}
    component_ids = np.array([mapping[g] for g in groups])
    folds = []
    for fold, (tr, va) in enumerate(GroupKFold(n_splits=3).split(x, y, component_ids)):
        # Undo original scaling then refit on fold training contexts only.
        raw_tr = x[tr].astype(np.float64) * config["scale"] + config["mean"]
        raw_va = x[va].astype(np.float64) * config["scale"] + config["mean"]
        mean, scale = raw_tr.mean(axis=(0, 1)), raw_tr.std(axis=(0, 1))
        scale[scale == 0] = 1
        tx, tv = ((raw_tr - mean) / scale).astype(np.float32), ((raw_va - mean) / scale).astype(np.float32)
        m, info = fit(tx, y[tr], tv, y[va], hidden=chosen["architecture"]["hidden_size"],
                      length=chosen["window_length"], epochs=min(args.epochs, 15),
                      batch_size=args.batch_size, lr=args.lr, seed=args.seed + fold, device=device)
        fr = clone(forest).fit(tx[:, -1], y[tr])
        fs = fr.predict_proba(tv[:, -1])[:, 1]
        folds.append({"fold": fold, "train_components": sorted(set(component_ids[tr].tolist())),
                      "validation_components": sorted(set(component_ids[va].tolist())),
                      "gru": metrics(y[va], scores_for(m, tv[:, -chosen['window_length']:].copy(), device), info["threshold"]),
                      "rf": metrics(y[va], fs, select_threshold(y[va], fs)),
                      "note": "inner validation diagnostic, checkpoint/threshold optimized on fold; not unbiased outer CV"})
        write_json(RESULTS / "training_group_diagnostics.json", folds)
    print("Training and validation selection complete; test remains unevaluated.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    train(parser.parse_args())
