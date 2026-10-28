"""Separate measured GRU, MAC/session and application timings from simulated EDF."""
import json
import time
from collections import Counter
import numpy as np
from src.ml.gru_sensor_model import FEATURES
from src.ml.skab_dataset import RAW, load_recording, ROOT, write_json
from src.ml.evaluate_gru_sensor_model import benchmark
from src.security import sensor_system as system
from src.security.source_sessions import authenticate_sender
from src.security.message_monitor import MessageMonitor


def main():
    import torch
    torch.set_num_threads(2)
    source = "SKAB_01"
    keys = {source: system.SENSOR_KEYS[source]}
    receiver = MessageMonitor(keys)
    handshake = benchmark(lambda: authenticate_sender(receiver.sessions, source, keys[source]))
    sender = authenticate_sender(receiver.sessions, source, keys[source])
    sequence = 0
    def verify():
        nonlocal sequence
        sequence += 1
        message, mac = sender.sign({"sensor_id": source, "sequence": sequence, "timestamp": sequence,
                                    "sensor_values": dict.fromkeys(FEATURES, 1.)})
        start = time.perf_counter_ns()
        result = receiver.verify(message, mac)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        assert result["valid"]
        return elapsed
    for _ in range(20): verify()
    times = [verify() for _ in range(200)]
    mac = {"median_ms": float(np.median(times)), "p95_ms": float(np.percentile(times, 95)),
           "warmup": 20, "repetitions": 200, "includes": "session lookup, MAC, replay checks; sender signing excluded"}
    group = "data/anomaly-free/anomaly-free.csv"
    x, _, timestamps = load_recording(RAW / group, nominal=True)
    health = system.health_monitor
    if health.predictor is None: raise ValueError("GRU unavailable")
    length = health.predictor.length
    sender = authenticate_sender(system.message_monitor.sessions, source, keys[source])
    rows = [{"sensor_id": source, "sensor_domain": "SKAB", "recording_id": group,
             "timestamp": int(timestamps[i]), "sensor_values": dict(zip(FEATURES, x[i].tolist()))}
            for i in range(length)]
    elapsed, outcomes = [], Counter()
    for i in range(220):
        health.commission_trusted_history(source, sender.session_id, group, rows[:-1])
        system.feature_tracker.reset(source)
        message, signature = sender.sign({**rows[-1], "sequence": i + 1, "distance_m": 12.})
        result = system.process_messages([{"message": message, "mac": signature, "arrival_time": 0,
             "execution_time": 3, "security_overhead": 1, "deadline": 20, "message_age_ms": 0}])
        if i >= 20:
            elapsed.append(result["application_processing_ms"])
            outcomes[result["messages"][0]["status"]] += 1
    write_json(ROOT / "results/gru/pipeline_latency.json", {"handshake": handshake,
        "message_verification": mac,
        "application": {"median_ms": float(np.median(elapsed)), "p95_ms": float(np.percentile(elapsed, 95)),
                        "warmup": 20, "repetitions": 200, "outcomes": dict(outcomes),
                        "protocol": "isolated repeated nominal candidate; trusted commissioning and signing outside timer"},
        "scheduler": {"unit": "simulation units", "execution": 3, "base_security": 1, "deadline": 20,
                      "measured_time_conversion": None},
        "cpu_threads": 2, "window_length": length})
    print(json.dumps(json.loads((ROOT / "results/gru/pipeline_latency.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
