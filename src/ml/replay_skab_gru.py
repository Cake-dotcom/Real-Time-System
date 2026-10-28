"""Explicit trusted-local commissioning demo; not an untrusted network endpoint."""
import json
import numpy as np
from src.ml.skab_dataset import RAW, META, DATA_FILES, FEATURES, digest, load_recording
from src.security.source_sessions import authenticate_sender


def commission_and_process(system):
    health = system.health_monitor
    if not hasattr(health, "predictor") or health.predictor is None:
        raise ValueError("GRU unavailable")
    group = "data/anomaly-free/anomaly-free.csv"
    source = "SKAB_01"
    lock = json.loads((META / "source_manifest.json").read_text())
    expected = next(r["sha256"] for r in lock["files"] if r["path"] == group)
    if digest((RAW / group).read_bytes()) != expected:
        raise ValueError("Commissioning source checksum failed")
    x, _, timestamps = load_recording(RAW / group, nominal=True)
    length = health.predictor.length
    # Choose first complete contiguous segment, without inspecting model predictions.
    start = next(i for i in range(len(x) - length + 1)
                 if all(0 < d <= 2 for d in np.diff(timestamps[i:i+length])))
    sender = authenticate_sender(system.message_monitor.sessions, source, system.SENSOR_KEYS[source])
    observations = [{"sensor_id": source, "recording_id": group, "sensor_domain": "SKAB",
                     "timestamp": int(timestamps[i]), "sensor_values": dict(zip(FEATURES, x[i].tolist()))}
                    for i in range(start, start + length)]
    health.commission_trusted_history(source, sender.session_id, group, observations[:-1])
    system.feature_tracker.reset(source)
    sequence = system.message_monitor.last_sequence.get(source, 0) + 1
    # Distance is separate simulator input; never substitute it for a physical SKAB feature.
    message, mac = sender.sign({**observations[-1], "sequence": sequence, "distance_m": 12.0})
    return system.process_messages([{"message": message, "mac": mac, "arrival_time": 0,
        "execution_time": 3, "security_overhead": 1, "deadline": 20, "message_age_ms": 0}])


if __name__ == "__main__":
    from src.security import sensor_system
    print(json.dumps(commission_and_process(sensor_system), indent=2))
