import json
import numpy as np
import pytest
import torch
from src.ml.gru_sensor_model import GRUClassifier, GRUPredictor, FEATURES, save_artifact
from src.ml.train_gru_sensor_model import fit


@pytest.fixture
def artifact(tmp_path):
    torch.set_num_threads(2)
    model = GRUClassifier(hidden_size=8)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.head[1].bias[0] = 3
    metadata = {"format_version": 1, "domain": "SKAB water circulation testbed",
                "features": FEATURES, "classes": ["normal", "anomalous"],
                "window_length": 4, "threshold": 0.5, "mean": [1.] * 8,
                "scale": [2.] * 8,
                "architecture": {"input_size": 8, "hidden_size": 8, "layers": 1, "dropout": 0.2}}
    path = tmp_path / "gru.pt"
    save_artifact(path, model, metadata)
    return path


def test_shapes_cpu_roundtrip_and_preprocessing(artifact):
    p = GRUPredictor(artifact)
    assert p.model(torch.zeros(3, 4, 8)).shape == (3, 2)
    x = np.arange(32).reshape(4, 8)
    np.testing.assert_allclose(p.transform(x, FEATURES), (x - 1) / 2)
    output = p.predict(x)
    assert output["prediction"] == "normal" and 0 < output["anomaly_score"] < 1
    assert p.model.training is False
    assert np.isfinite(output["inference_ms"])


@pytest.mark.parametrize("kind", ["short", "nan", "inf", "order", "shape"])
def test_invalid_inputs_fail(artifact, kind):
    p = GRUPredictor(artifact)
    x = np.ones((4, 8))
    features = FEATURES
    if kind == "short": x = x[:2]
    if kind == "shape": x = x[:, :7]
    if kind == "nan": x[0, 0] = np.nan
    if kind == "inf": x[0, 0] = np.inf
    if kind == "order": features = FEATURES[::-1]
    with pytest.raises(ValueError):
        p.predict(x, features)


def test_metadata_and_checksum_fail(artifact):
    meta_path = artifact.with_suffix(".json")
    meta = json.loads(meta_path.read_text())
    meta["features"] = FEATURES[::-1]
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError): GRUPredictor(artifact)
    meta["features"] = FEATURES
    meta_path.write_text(json.dumps(meta))
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError): GRUPredictor(artifact)


def test_small_training_finite_and_reproducible():
    torch.set_num_threads(2)
    x = np.random.default_rng(42).normal(size=(40, 4, 8)).astype(np.float32)
    y = np.tile([0, 1], 20)
    first, info = fit(x, y, x[:10], y[:10], hidden=8, length=4, epochs=2, batch_size=10)
    second, repeat = fit(x, y, x[:10], y[:10], hidden=8, length=4, epochs=2, batch_size=10)
    assert info["history"] == repeat["history"]
    for a, b in zip(first.parameters(), second.parameters()):
        assert torch.isfinite(a).all() and torch.equal(a, b)
    assert info["best_epoch"] in [1, 2]
    with pytest.raises(ValueError): fit(x[:0], y[:0], x, y)
