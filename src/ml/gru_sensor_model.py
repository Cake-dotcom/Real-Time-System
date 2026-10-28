"""Causal GRU and strict, dataset-independent CPU inference artifact interface."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

FEATURES = ["Accelerometer1RMS", "Accelerometer2RMS", "Current", "Pressure",
            "Temperature", "Thermocouple", "Voltage", "Volume Flow RateRMS"]
ARTIFACT = Path(__file__).resolve().parents[2] / "models/gru_sensor_health.pt"


class GRUClassifier(nn.Module):
    def __init__(self, input_size=8, hidden_size=64, layers=1, dropout=0.2):
        super().__init__()
        self.gru = nn.GRU(input_size, hidden_size, num_layers=layers,
                          dropout=dropout if layers > 1 else 0.0, batch_first=True)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden_size, 2))

    def forward(self, x):
        _, hidden = self.gru(x)
        return self.head(hidden[-1])


def save_artifact(path, model, metadata):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, path)
    metadata = {**metadata, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


class GRUPredictor:
    def __init__(self, path=ARTIFACT):
        path = Path(path)
        self.metadata = meta = json.loads(path.with_suffix(".json").read_text())
        if (meta["format_version"] != 1 or meta["features"] != FEATURES
                or meta["classes"] != ["normal", "anomalous"]
                or meta["domain"] != "SKAB water circulation testbed"
                or not isinstance(meta["window_length"], int)
                or not 1 <= meta["window_length"] <= 256
                or not 0 < meta["threshold"] < 1):
            raise ValueError("Incompatible GRU metadata")
        self.length = meta["window_length"]
        self.mean = np.asarray(meta["mean"], dtype=np.float64)
        self.scale = np.asarray(meta["scale"], dtype=np.float64)
        if (self.mean.shape != (8,) or self.scale.shape != (8,)
                or not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all()
                or np.any(self.scale <= 0)):
            raise ValueError("Invalid preprocessing metadata")
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            raise ValueError("GRU checkpoint checksum mismatch")
        architecture = meta["architecture"]
        if (architecture["input_size"] != 8 or not 1 <= architecture["hidden_size"] <= 256
                or architecture["layers"] not in [1, 2] or not 0 <= architecture["dropout"] < 1):
            raise ValueError("Invalid architecture")
        self.model = GRUClassifier(**architecture)
        # Bounded CPU parallelism for the small batch-one online network.
        torch.set_num_threads(2)
        self.model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=True)
        if any(not torch.isfinite(p).all() for p in self.model.parameters()):
            raise ValueError("Nonfinite model weights")
        self.model.eval()

    def transform(self, values, feature_order):
        if list(feature_order) != FEATURES:
            raise ValueError("Feature order mismatch")
        x = np.asarray(values, dtype=np.float64)
        if x.shape != (self.length, 8) or not np.isfinite(x).all():
            raise ValueError("Missing history or invalid measurement shape/value")
        x = ((x - self.mean) / self.scale).astype(np.float32)
        if not np.isfinite(x).all():
            raise ValueError("Scaled values overflow")
        return x

    def predict(self, values, feature_order=FEATURES):
        started = time.perf_counter_ns()
        x = self.transform(values, feature_order)
        with torch.inference_mode():
            logits = self.model(torch.from_numpy(x).unsqueeze(0))
            if logits.shape != (1, 2) or not torch.isfinite(logits).all():
                raise ValueError("Invalid model output")
            score = float(logits.softmax(-1)[0, 1])
        return {"prediction": "anomalous" if score >= self.metadata["threshold"] else "normal",
                "anomaly_score": score, "threshold": self.metadata["threshold"],
                "probabilities": {"normal": 1 - score, "anomalous": score},
                "inference_ms": (time.perf_counter_ns() - started) / 1e6}
