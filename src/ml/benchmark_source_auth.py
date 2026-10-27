"""Measured in-process source authentication benchmark (no network or ML timing)."""
import argparse
import hashlib
import json
import math
import platform
from pathlib import Path
import statistics
import time

from src.security.message_monitor import MessageMonitor
from src.security.source_sessions import authenticate_sender


def workload(count):
    messages = []
    sequences = {source: 0 for source in ("LIDAR_01", "RADAR_01", "CAMERA_01")}
    for index in range(count):
        source = list(sequences)[index % 3]
        sequences[source] += 1
        body = {"sensor_id": source, "sequence": sequences[source],
                "timestamp": 1000 + index, "distance_m": 12.0 + index % 3}
        messages.append((body, "valid"))
        if index % 20 == 0:
            messages.append((dict(body), "replay"))
            messages.append((dict(body), "tampered"))
    return messages


def run_once(messages, mode):
    keys = {source: "benchmark-demo-" + source for source in ("LIDAR_01", "RADAR_01", "CAMERA_01")}
    monitor = MessageMonitor(keys)
    senders = {}
    elapsed = []
    receiver_elapsed = []
    accepted = violations = 0
    # Initialization is excluded in both modes; all handshakes and per-message
    # signing/verification are included. Payload generation is excluded equally.
    cpu_started = time.process_time_ns()
    total_started = time.perf_counter_ns()
    for body, scenario in messages:
        before = monitor.sessions.metrics["handshake_processing_ns"] + monitor.sessions.metrics["message_verification_ns"]
        started = time.perf_counter_ns()
        source = body["sensor_id"]
        if mode == "full_auth_every_message" or source not in senders:
            senders[source] = authenticate_sender(monitor.sessions, source, keys[source])
        message, mac = senders[source].sign(body)
        if scenario == "tampered":
            message["distance_m"] += 1
        result = monitor.verify(message, mac)
        elapsed.append(time.perf_counter_ns() - started)
        after = monitor.sessions.metrics["handshake_processing_ns"] + monitor.sessions.metrics["message_verification_ns"]
        receiver_elapsed.append(after - before)
        accepted += int(result["valid"])
        violations += int(result["valid"] and scenario != "valid")
        if result["valid"] != (scenario == "valid"):
            raise AssertionError("Authentication outcome differs from workload expectation")
    total = time.perf_counter_ns() - total_started
    cpu = time.process_time_ns() - cpu_started
    expected_mac_checks = len(messages)
    assert monitor.sessions.metrics["mac_verifications"] == expected_mac_checks
    return {"elapsed_ns": elapsed, "receiver_elapsed_ns": receiver_elapsed,
            "total_elapsed_ns": total, "cpu_ns": cpu, "accepted": accepted,
            "security_violations": violations, "metrics": dict(monitor.sessions.metrics)}


def percentiles(values):
    ordered = sorted(values)
    return {"mean_us": statistics.mean(values) / 1000,
            "median_us": statistics.median(values) / 1000,
            "p95_us": ordered[max(0, math.ceil(.95 * len(ordered)) - 1)] / 1000}


def benchmark(count=1000, repetitions=10):
    if count < 3 or repetitions < 2:
        raise ValueError("Use at least three valid messages and two repetitions")
    messages = workload(count)
    modes = ("full_auth_every_message", "session_reuse")
    for mode in modes:
        run_once(workload(30), mode)  # Unreported warmup, real cryptographic nonces.
    runs = {mode: [] for mode in modes}
    for repeat in range(repetitions):
        for mode in (modes if repeat % 2 == 0 else modes[::-1]):
            runs[mode].append(run_once(messages, mode))
    results = {}
    for mode, data in runs.items():
        latency = [v for run in data for v in run["elapsed_ns"]]
        receiver_latency = [v for run in data for v in run["receiver_elapsed_ns"]]
        results[mode] = {
            "exchange_latency": percentiles(latency),
            "receiver_authentication_latency": percentiles(receiver_latency),
            "total_elapsed_ms": sum(run["total_elapsed_ns"] for run in data) / 1e6,
            "total_cpu_ms": sum(run["cpu_ns"] for run in data) / 1e6,
            "total_receiver_authentication_ms": sum(receiver_latency) / 1e6,
            "accepted_per_repetition": data[0]["accepted"],
            "accepted_security_violations": sum(run["security_violations"] for run in data),
            "metrics_totals": {key: sum(run["metrics"][key] for run in data) for key in data[0]["metrics"]},
            "per_repetition_mean_us": [statistics.mean(run["elapsed_ns"]) / 1000 for run in data],
        }
    base, reuse = (results[mode] for mode in modes)
    return {"method": "Alternating paired runs; full proof exchange every message versus session reuse. Both MAC-verify every message and enforce source-wide sequence monotonicity across reauthentication.",
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "timer": "perf_counter_ns elapsed; process_time_ns CPU"},
            "valid_messages_per_repetition": count, "attempts_per_repetition": len(messages),
            "repetitions": repetitions, "warmup_valid_messages_per_mode": 30,
            "workload_sha256": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
            "results": results,
            "receiver_overhead_reduction_percent": 100 * (1 - reuse["total_receiver_authentication_ms"] / base["total_receiver_authentication_ms"]),
            "exchange_mean_reduction_percent": 100 * (1 - reuse["exchange_latency"]["mean_us"] / base["exchange_latency"]["mean_us"]),
            "limitations": "Local Python simulation, no network/ECU timing or formal guarantees. Nonces/session IDs necessarily differ; semantic payloads and attacks are identical. Receiver timing excludes sender proof/signing; exchange latency includes both. Measurements are not inserted into EDF costs."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=1000)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("results/source_auth/benchmark.json"))
    args = parser.parse_args()
    report = benchmark(args.messages, args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
