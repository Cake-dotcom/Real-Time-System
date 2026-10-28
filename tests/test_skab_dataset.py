import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ml import skab_dataset as skab


def frame(rows=80, offset=0, nominal=False):
    data = pd.DataFrame({"datetime": pd.date_range("2020-01-01", periods=rows, freq="s").strftime("%Y-%m-%d %H:%M:%S")})
    for i, name in enumerate(skab.FEATURES):
        data[name] = np.arange(rows) + i + offset
    if not nominal:
        data["anomaly"] = [0] * (rows // 2) + [1] * (rows - rows // 2)
        data["changepoint"] = 0
    return data


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, sep=";", index=False)


@pytest.fixture
def corpus(tmp_path):
    raw, meta, output = (tmp_path / name for name in ["raw", "meta", "processed"])
    records = []
    for i, name in enumerate(skab.SOURCE_FILES):
        path = raw / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name in skab.DATA_FILES:
            save(path, frame(offset=i, nominal="anomaly-free" in name))
        else:
            path.write_text("source fixture")
        records.append({"path": name, "sha256": skab.digest(path.read_bytes())})
    skab.write_json(meta / "source_manifest.json", {"commit": skab.COMMIT, "files": records})
    return raw, meta, output


def test_schema_labels_and_nominal_mapping(tmp_path):
    path = tmp_path / "input.csv"
    save(path, frame())
    x, y, times = skab.load_recording(path)
    assert x.shape == (80, 8) and y.tolist() == [0] * 40 + [1] * 40
    assert np.all(np.diff(times) == 1)
    save(path, frame(nominal=True))
    assert not skab.load_recording(path, nominal=True)[1].any()
    with pytest.raises(ValueError):
        skab.load_recording(path)


@pytest.mark.parametrize("corruption", ["missing", "nan", "inf", "text", "label", "changepoint", "duplicate", "reverse", "time", "extra", "empty"])
def test_malformed_records_fail(tmp_path, corruption):
    data = frame()
    if corruption == "missing":
        data = data.drop(columns=[skab.FEATURES[0]])
    elif corruption in ["nan", "inf", "text"]:
        data[skab.FEATURES[0]] = data[skab.FEATURES[0]].astype(object)
        data.loc[1, skab.FEATURES[0]] = {"nan": np.nan, "inf": np.inf, "text": "invalid"}[corruption]
    elif corruption in ["label", "changepoint"]:
        data.loc[1, "anomaly" if corruption == "label" else "changepoint"] = 2
    elif corruption == "duplicate":
        data.loc[1, "datetime"] = data.loc[0, "datetime"]
    elif corruption == "reverse":
        data = data.iloc[::-1]
    elif corruption == "time":
        data.loc[1, "datetime"] = "invalid"
    elif corruption == "extra":
        data["future_label"] = 1
    else:
        data = data.iloc[:0]
    path = tmp_path / "bad.csv"
    save(path, data)
    with pytest.raises((ValueError, TypeError)):
        skab.load_recording(path)


def test_window_gaps_and_parameters():
    times = np.array([0, 1, 3, 4, 20, 21, 22, 23])
    assert skab.window_ends(times, 3, 1).tolist() == [2, 3, 6, 7]
    assert skab.window_ends(times, 3, 2).tolist() == [2, 6]
    assert not len(skab.window_ends(times, 20, 1))
    with pytest.raises(ValueError):
        skab.window_ends(times, 0, 1)


def test_overlapping_recordings_stay_together():
    recordings = {}
    for i, group in enumerate(skab.DATA_FILES):
        recordings[group] = (np.full((3, 8), i, dtype=float), np.zeros(3), np.arange(3))
    nominal, overlap, chained = skab.DATA_FILES[:3]
    recordings[overlap] = recordings[nominal]
    recordings[chained] = recordings[overlap]
    components = skab.recording_components(recordings)
    assert len(components) == len(skab.DATA_FILES) - 2
    splits = skab.split_groups(skab.DATA_FILES, components=components)
    assert {nominal, overlap, chained} <= set(splits["train"])
    assert splits == skab.split_groups(skab.DATA_FILES, components=components)


def test_missing_source_fails(corpus):
    raw, meta, output = corpus
    (raw / skab.DATA_FILES[0]).unlink()
    with pytest.raises(FileNotFoundError):
        skab.prepare(raw, meta, output)


def test_conflicting_duplicate_targets_are_excluded(corpus):
    raw, meta, output = corpus
    nominal = skab.DATA_FILES[0]
    overlap = skab.DATA_FILES[1]
    # Identical physical samples, nominal recording versus anomalous annotation.
    save(raw / overlap, frame(offset=0))
    lock = json.loads((meta / "source_manifest.json").read_text())
    for entry in lock["files"]:
        if entry["path"] == overlap:
            entry["sha256"] = skab.digest((raw / overlap).read_bytes())
    skab.write_json(meta / "source_manifest.json", lock)
    report = skab.prepare(raw, meta, output)
    assert report["ambiguous_unique_samples"] == 40
    assert report["recordings"][overlap]["excluded_ambiguous_windows"] == 17
    assert report["recordings"][nominal]["excluded_ambiguous_windows"] == 17
    assert report["recordings"][overlap]["split"] == "train"
    assert all(info["group"] not in {nominal, overlap} for _, _, info in skab.iter_windows(output))


def test_reproducible_group_splits_scaling_and_causal_windows(corpus):
    raw, meta, output = corpus
    first = skab.prepare(raw, meta, output)
    config = json.loads((meta / "config.json").read_text())
    manifests = {name: json.loads((meta / f"{name}.json").read_text()) for name in ["train", "validation", "test"]}
    sets = [set(e["group"] for e in entries) for entries in manifests.values()]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert set.union(*sets) == set(skab.DATA_FILES)
    training = np.concatenate([skab.load_recording(raw / group, nominal="anomaly-free" in group)[0] for group in config["scaler_fit_groups"]])
    np.testing.assert_allclose(config["mean"], training.mean(axis=0))
    np.testing.assert_allclose(config["scale"], training.std(axis=0))
    for split in manifests:
        samples = list(skab.iter_windows(output, split))
        assert len(samples) == first["splits"][split]["windows"]
        for x, label, info in samples:
            original, labels, times = skab.load_recording(raw / info["group"], nominal="anomaly-free" in info["group"])
            start, end = info["start_row"], info["end_row"]
            np.testing.assert_allclose(x, ((original[start:end + 1] - config["mean"]) / config["scale"]).astype(np.float32))
            assert x.shape == (64, 8) and label == labels[end]
            assert info["timestamp"] == times[end]
            assert info["timestamps"].tolist() == times[start:end + 1].tolist()
    second = skab.prepare(raw, meta, output)
    assert second == first
    assert config == json.loads((meta / "config.json").read_text())
    assert manifests == {name: json.loads((meta / f"{name}.json").read_text()) for name in manifests}
    # Extreme held-out values must not affect the fitted transformation.
    held_out = next(iter(sets[2]))
    save(raw / held_out, frame(offset=1000000))
    lock = json.loads((meta / "source_manifest.json").read_text())
    for entry in lock["files"]:
        if entry["path"] == held_out:
            entry["sha256"] = skab.digest((raw / held_out).read_bytes())
    skab.write_json(meta / "source_manifest.json", lock)
    skab.prepare(raw, meta, output)
    assert config == json.loads((meta / "config.json").read_text())


def test_original_tampering_rejected(corpus):
    raw, meta, output = corpus
    (raw / skab.DATA_FILES[0]).write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        skab.prepare(raw, meta, output)


def test_processed_tampering_and_leakage_rejected(corpus):
    raw, meta, output = corpus
    skab.prepare(raw, meta, output)
    train = json.loads((output / "train.json").read_text())
    test = json.loads((output / "test.json").read_text())
    skab.write_json(output / "test.json", test + [train[0]])
    with pytest.raises(ValueError, match="leakage"):
        next(skab.iter_windows(output))
    skab.write_json(output / "test.json", test)
    (output / train[0]["file"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        next(skab.iter_windows(output))
