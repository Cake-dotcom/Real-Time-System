"""Offline SKAB acquisition/preparation; deliberately separate from production inference.

Run ``python -m src.ml.skab_dataset acquire`` then ``... prepare``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "b2c0d46c2971dcbfe71e26087b6d231998bb91c2"
BASE = f"https://raw.githubusercontent.com/waico/SKAB/{COMMIT}/"
RAW = ROOT / "data/raw/skab"
META = ROOT / "data/skab"
PROCESSED = ROOT / "data/processed/skab"
FEATURES = ["Accelerometer1RMS", "Accelerometer2RMS", "Current", "Pressure",
            "Temperature", "Thermocouple", "Voltage", "Volume Flow RateRMS"]
DATA_FILES = (["data/anomaly-free/anomaly-free.csv"]
              + [f"data/{family}/{i}.csv" for family, indices in
                 [("other", range(1, 15)), ("valve1", range(16)), ("valve2", range(4))]
                 for i in indices])
SOURCE_FILES = DATA_FILES + ["README.md", "data/README.md", "LICENSE"]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def acquire(raw: Path = RAW, metadata: Path = META) -> dict:
    """Download pinned originals. Never replace differing existing bytes."""
    manifest_path = metadata / "source_manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    records = []
    for relative in SOURCE_FILES:
        url = BASE + relative
        with urlopen(url, timeout=60) as response:
            content = response.read()
        record = {"path": relative, "url": url, "bytes": len(content), "sha256": digest(content)}
        if previous:
            expected = {r["path"]: r for r in previous["files"]}
            if record != expected.get(relative):
                raise ValueError(f"Upstream content differs from lock: {relative}")
        destination = raw / relative
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite changed original: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(content)
        records.append(record)
    manifest = {"dataset": "Skoltech Anomaly Benchmark (SKAB)", "version": "v0.9",
                "commit": COMMIT, "access_date": "2026-10-27", "files": records}
    write_json(manifest_path, manifest)
    return manifest


def load_recording(path: Path, *, nominal: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Strict schema and chronological validation; no sorting, filling or label guessing."""
    frame = pd.read_csv(path, sep=";")
    expected = ["datetime"] + FEATURES + ([] if nominal else ["anomaly", "changepoint"])
    if list(frame.columns) != expected or frame.empty:
        raise ValueError(f"Invalid schema or empty recording: {path}")
    timestamps = pd.to_datetime(frame["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    if timestamps.isna().any():
        raise ValueError(f"Missing timestamp: {path}")
    times = timestamps.to_numpy(dtype="datetime64[s]").astype(np.int64)
    if np.any(np.diff(times) <= 0):
        raise ValueError(f"Non-increasing timestamps: {path}")
    values = frame[FEATURES].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError(f"Missing or nonfinite measurement: {path}")
    if nominal:
        labels = np.zeros(len(frame), dtype=np.int8)
    else:
        for column in ["anomaly", "changepoint"]:
            if not frame[column].isin([0, 1]).all():
                raise ValueError(f"Invalid {column} label: {path}")
        labels = frame["anomaly"].to_numpy(dtype=np.int8)
    return values, labels, times


def recording_components(recordings: dict) -> list[list[str]]:
    """Connect files sharing a timestamp and all eight measurements (even differing labels)."""
    parent = {name: name for name in recordings}

    def find(name):
        while parent[name] != name:
            name = parent[name]
        return name

    seen = {}
    for name in sorted(recordings):
        values, _, times = recordings[name]
        for row, timestamp in zip(values, times):
            key = (int(timestamp), row.tobytes())
            if key in seen:
                parent[find(name)] = find(seen[key])
            seen[key] = name
    components = {}
    for name in sorted(recordings):
        components.setdefault(find(name), []).append(name)
    return sorted(components.values())


def split_groups(groups: list[str], seed: int = 42, components=None) -> dict[str, list[str]]:
    """Assign whole recordings within each condition; nominal-only recording trains only."""
    rng = np.random.default_rng(seed)
    result = {name: [] for name in ["train", "validation", "test"]}
    components = components if components is not None else [[g] for g in sorted(groups)]
    units = {min(component): component for component in components}
    if sorted(g for component in components for g in component) != sorted(groups):
        raise ValueError("Components must partition the recordings")
    for family in sorted({Path(group).parent.name for group in units}):
        members = sorted(group for group in units if Path(group).parent.name == family)
        if family == "anomaly-free":
            result["train"].extend(g for member in members for g in units[member])
            continue
        if len(members) < 3:
            raise ValueError("Each anomalous experiment family needs at least three groups")
        rng.shuffle(members)
        held = max(1, int(len(members) * 0.2))
        result["test"].extend(g for member in members[:held] for g in units[member])
        result["validation"].extend(g for member in members[held:2 * held] for g in units[member])
        result["train"].extend(g for member in members[2 * held:] for g in units[member])
    return {name: sorted(members) for name, members in result.items()}


def window_ends(times: np.ndarray, length: int, stride: int) -> np.ndarray:
    """64 observations are not 64 seconds: retain 1/2s steps, break on larger gaps."""
    if length < 1 or stride < 1:
        raise ValueError("Window length and stride must be positive")
    boundaries = np.r_[0, np.flatnonzero((np.diff(times) > 2) | (np.diff(times) <= 0)) + 1, len(times)]
    chunks = [np.arange(start + length - 1, end, stride, dtype=np.int64)
              for start, end in zip(boundaries[:-1], boundaries[1:])]
    return np.concatenate(chunks) if chunks else np.array([], dtype=np.int64)


def prepare(raw: Path = RAW, metadata: Path = META, output: Path = PROCESSED,
            *, length: int = 64, stride: int = 1, seed: int = 42) -> dict:
    if length < 1 or stride < 1:
        raise ValueError("Window length and stride must be positive")
    source = json.loads((metadata / "source_manifest.json").read_text())
    if source["commit"] != COMMIT or {r["path"] for r in source["files"]} != set(SOURCE_FILES):
        raise ValueError("Unexpected source manifest")
    recordings = {}
    hashes = set()
    for record in source["files"]:
        path = raw / record["path"]
        if digest(path.read_bytes()) != record["sha256"]:
            raise ValueError(f"Original checksum mismatch: {path}")
        if record["path"] in DATA_FILES:
            if record["sha256"] in hashes:
                raise ValueError("Duplicate original recordings")
            hashes.add(record["sha256"])
            recordings[record["path"]] = load_recording(path, nominal="anomaly-free" in record["path"])
    components = recording_components(recordings)
    splits = split_groups(list(recordings), seed, components)
    seen_samples = {}
    duplicate_samples = 0
    conflicting_labels = 0
    ambiguous = set()
    for group in sorted(recordings):
        values, labels, times = recordings[group]
        for row, label, timestamp in zip(values, labels, times):
            key = (int(timestamp), row.tobytes())
            if key in seen_samples:
                duplicate_samples += 1
                conflicting_labels += int(seen_samples[key] != int(label))
                if seen_samples[key] != int(label):
                    ambiguous.add(key)
            seen_samples[key] = int(label)
    training = np.concatenate([recordings[group][0] for group in splits["train"]])
    mean, scale = training.mean(axis=0), training.std(axis=0)
    scale[scale == 0] = 1.0
    config = {"dataset": "SKAB", "commit": COMMIT, "features": FEATURES,
              "label_mapping": {"0": "normal", "1": "anomalous"},
              "window_length": length, "stride": stride, "seed": seed,
              "target": "original anomaly label at window endpoint",
              "missing_values": "reject", "maximum_step_seconds": 2,
              "resampling": "none; windows count observations, not seconds",
              "ambiguous_labels": "exclude targets with conflicting duplicate labels; retain context measurements",
              "mean": mean.tolist(), "scale": scale.tolist(),
              "scaler_fit_groups": splits["train"], "synthetic_augmentation": False,
              "overlap_components": components}
    report = {"splits": {}, "recordings": {}, "features": FEATURES,
              "overlap_components": components, "component_count": len(components),
              "duplicate_samples": duplicate_samples,
              "unique_timestamp_measurement_samples": len(seen_samples),
              "conflicting_duplicate_labels": conflicting_labels,
              "ambiguous_unique_samples": len(ambiguous),
              "missing_or_nonfinite_values": 0,
              "numpy_version": np.__version__, "pandas_version": pd.__version__}
    output.mkdir(parents=True, exist_ok=True)
    for split, groups in splits.items():
        entries = []
        totals = {"groups": len(groups), "rows": 0, "normal": 0, "anomalous": 0,
                  "windows": 0, "normal_windows": 0, "anomalous_windows": 0}
        for group in groups:
            values, labels, times = recordings[group]
            ends = window_ends(times, length, stride)
            valid_target = np.array([(int(t), row.tobytes()) not in ambiguous
                                     for row, t in zip(values, times)], dtype=bool)
            excluded_windows = int((~valid_target[ends]).sum())
            ends = ends[valid_target[ends]]
            filename = group.removeprefix("data/").replace("/", "__").removesuffix(".csv") + ".npz"
            standardized = ((values - mean) / scale).astype(np.float32)
            if not np.isfinite(standardized).all():
                raise ValueError("Nonfinite scaled features")
            np.savez(output / filename, x=standardized, y=labels, timestamps=times, ends=ends,
                     valid_target=valid_target)
            entries.append({"group": group, "file": filename,
                            "sha256": digest((output / filename).read_bytes()),
                            "rows": len(values), "windows": len(ends)})
            stats = {"rows": len(values), "normal": int((labels == 0).sum()),
                     "anomalous": int(labels.sum()), "windows": len(ends),
                     "normal_windows": int((labels[ends] == 0).sum()),
                     "anomalous_windows": int(labels[ends].sum())}
            for key, value in stats.items():
                totals[key] += value
            report["recordings"][group] = {**stats, "split": split,
                "start": str(np.datetime64(int(times[0]), "s")),
                "end": str(np.datetime64(int(times[-1]), "s")),
                "gaps_over_2_seconds": int((np.diff(times) > 2).sum()),
                "ambiguous_target_rows": int((~valid_target).sum()),
                "excluded_ambiguous_windows": excluded_windows,
                "step_seconds_counts": {str(int(k)): int(v) for k, v in zip(*np.unique(np.diff(times), return_counts=True))},
                "label_origin": "documented nominal recording" if "anomaly-free" in group else "original anomaly column"}
        if not totals["windows"]:
            raise ValueError(f"No usable windows in {split}")
        report["splits"][split] = totals
        totals["components"] = sum(component[0] in groups for component in components)
        write_json(output / f"{split}.json", entries)
        write_json(metadata / f"{split}.json", entries)
    write_json(output / "config.json", config)
    write_json(metadata / "config.json", config)
    write_json(metadata / "validation_report.json", report)
    return report


def iter_windows(directory: Path = PROCESSED, split: str = "train"):
    """Yield (float32[T,8], endpoint label, provenance), without a framework dependency."""
    if split not in {"train", "validation", "test"}:
        raise ValueError("Unknown split")
    config = json.loads((directory / "config.json").read_text())
    length = config["window_length"]
    if config["features"] != FEATURES or length < 1:
        raise ValueError("Incompatible feature configuration")
    manifests = {s: json.loads((directory / f"{s}.json").read_text())
                 for s in ["train", "validation", "test"]}
    groups = [entry["group"] for entries in manifests.values() for entry in entries]
    if len(groups) != len(set(groups)):
        raise ValueError("Group leakage in manifests")
    owners = {entry["group"]: name for name, entries in manifests.items() for entry in entries}
    if any(len({owners.get(group) for group in component}) != 1
           for component in config["overlap_components"]):
        raise ValueError("Shared recording leakage in manifests")
    for entry in manifests[split]:
        path = directory / entry["file"]
        if path.resolve().parent != directory.resolve() or digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError("Invalid processed file or checksum")
        with np.load(path, allow_pickle=False) as recording:
            x, y, times, ends = (recording[k] for k in ["x", "y", "timestamps", "ends"])
            valid_target = recording["valid_target"]
            if valid_target.shape != y.shape or valid_target.dtype != np.bool_:
                raise ValueError("Invalid target eligibility mask")
            expected_ends = window_ends(times, length, config["stride"])
            expected_ends = expected_ends[valid_target[expected_ends]]
            if (x.shape != (len(y), len(FEATURES)) or len(times) != len(y)
                    or not np.isfinite(x).all() or not np.isin(y, [0, 1]).all()
                    or np.any(np.diff(times) <= 0)
                    or not np.array_equal(ends, expected_ends)):
                raise ValueError("Invalid processed recording")
            for end in ends:
                start = int(end) - length + 1
                yield x[start:end + 1].copy(), int(y[end]), {
                    "group": entry["group"], "start_row": start, "end_row": int(end),
                    "timestamp": int(times[end]), "timestamps": times[start:end + 1].copy(),
                    "label_origin": "documented nominal recording" if "anomaly-free" in entry["group"] else "original anomaly column"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["acquire", "prepare"])
    args = parser.parse_args()
    result = acquire() if args.action == "acquire" else prepare()
    print(json.dumps(result.get("splits", {"files": len(result.get("files", []))}), indent=2))
