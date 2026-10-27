"""Small synthetic comparison through the real pipeline, for demonstration.

Baseline overrides are scoped to this offline experiment. Mandatory gates,
health rejection, history rules and EDF are identical in all three modes.
"""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from src.security import sensor_system as system
from src.security.source_sessions import authenticate_sender
from src.security.message_monitor import MessageMonitor
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor
from src.security.risk_policy import assess_sensor_risk
from src.security.validation_config import SIMULATED_EXTRA_COSTS


def workloads():
    batches = []
    for deadline in (4, 5, 6, 10, 20):
        batch = []
        for sensor in ("LIDAR_01", "RADAR_01", "CAMERA_01"):
            message = {"sensor_id": sensor, "sequence": 1, "timestamp": 1000, "distance_m": 12.0}
            batch.append({"message": message,
                          "arrival_time": 0, "execution_time": 3, "security_overhead": 1,
                          "deadline": deadline, "message_age_ms": 5.0, "scenario": "normal"})
        tampered = copy.deepcopy(batch[0])
        tampered["scenario"] = "tampering"
        replay = copy.deepcopy(batch[1])
        replay["scenario"] = "replay"
        faulty = copy.deepcopy(batch[2])
        faulty["message"].update(sequence=2, distance_m=250.0)
        faulty["scenario"] = "sensor_fault"
        unauthenticated = copy.deepcopy(batch[0])
        unauthenticated["scenario"] = "unauthenticated"
        unknown = copy.deepcopy(batch[0])
        unknown["message"]["sensor_id"] = "UNKNOWN"
        unknown["scenario"] = "unknown_source"
        batch.extend([tampered, replay, faulty, unauthenticated, unknown])
        batches.append(batch)
    return batches


def run_comparison():
    batches = workloads()
    digest = hashlib.sha256(json.dumps(batches, sort_keys=True).encode()).hexdigest()
    summary = {}
    for mode in ("base_edf", "fixed_validation", "risk_adaptive"):
        def policy(health, features):
            decision = assess_sensor_risk(health, features)
            if mode == "risk_adaptive" or decision.validation_level in {"reject", "unavailable"}:
                return decision
            return replace(decision,
                           required_checks=(("reading_plausibility",) if mode == "base_edf" else
                                            ("reading_plausibility", "temporal_consistency", "stability_check")),
                           simulated_extra_cost=(0.0 if mode == "base_edf" else SIMULATED_EXTRA_COSTS["high"]))
        stats = {"workload_sha256": digest, "submitted": 0, "accepted": 0,
                 "scheduled": 0, "deadline_misses": 0, "deferred": 0,
                 "scheduled_extra_cost": 0.0, "scheduled_handshake_cost": 0.0,
                 "scheduled_total_security_overhead": 0.0, "policy_escalations": 0,
                 "rejected_excluding_deferred": 0,
                 "accepted_security_violations": 0, "by_scenario": {}, "by_health_prediction": {}}
        for batch in batches:
            monitor = MessageMonitor(system.SENSOR_KEYS)
            senders = {source: authenticate_sender(monitor.sessions, source, key)
                       for source, key in system.SENSOR_KEYS.items()}
            prepared = copy.deepcopy(batch)
            for candidate in prepared:
                source = candidate["message"]["sensor_id"]
                if source not in senders:
                    candidate["mac"] = "invalid"
                    continue
                candidate["message"], candidate["mac"] = senders[source].sign(candidate["message"])
                if candidate["scenario"] == "tampering":
                    candidate["message"]["distance_m"] += 1
                elif candidate["scenario"] == "unauthenticated":
                    candidate["message"].pop("session_id")
            with (patch.object(system, "message_monitor", monitor),
                  patch.object(system, "feature_tracker", SensorFeatureTracker()),
                  patch.object(system, "health_monitor", SensorHealthMonitor()),
                  patch.object(system, "assess_sensor_risk", policy)):
                result = system.process_messages(prepared)
            stats["scheduled"] += len(result["schedule"]["results"])
            stats["deadline_misses"] += sum(not r["deadline_met"] for r in result["schedule"]["results"])
            stats["deferred"] += len(result["schedule"]["deferred_sensors"])
            scheduled_ids = {r["task_id"] for r in result["schedule"]["results"]}
            for source, decision in zip(batch, result["messages"]):
                stats["submitted"] += 1
                stats["accepted"] += int(decision["accepted"])
                stats["rejected_excluding_deferred"] += int(not decision["accepted"] and decision["status"] != "DEFERRED")
                if decision.get("task_id") in scheduled_ids:
                    stats["scheduled_extra_cost"] += decision["simulated_extra_cost"]
                    stats["scheduled_handshake_cost"] += decision["simulated_handshake_cost"]
                    stats["scheduled_total_security_overhead"] += decision["total_security_overhead"]
                selected = decision.get("policy")
                stats["policy_escalations"] += int(bool(selected and decision["simulated_extra_cost"] > 0))
                stats["accepted_security_violations"] += int(decision["accepted"] and (
                    decision["source_authentication"] != "passed"
                    or decision["authentication"] != "passed" or decision["replay"] != "passed"))
                for key, value in (("by_scenario", source["scenario"]),
                                   ("by_health_prediction", decision.get("health", {}).get("prediction", "not_evaluated"))):
                    counts = stats[key].setdefault(value, {"accepted": 0, "rejected": 0})
                    counts["accepted" if decision["accepted"] else "rejected"] += 1
        stats["deadline_miss_rate_of_scheduled"] = stats["deadline_misses"] / stats["scheduled"] if stats["scheduled"] else 0
        summary[mode] = stats
    return {"description": "40 synthetic messages, five independent batches; actual saved health model; same semantic payloads, source sessions, MAC and replay gates in every mode.",
            "limitations": "Illustrative workloads, not performance/generalization evidence. Rejection CPU cost is unmodeled. Base and fixed modes retain the same fail-closed health gates. Health groups are predictions, not ground-truth classes.",
            "modes": summary}


def main():
    report = run_comparison()
    output = Path("results/source_auth")
    output.mkdir(parents=True, exist_ok=True)
    (output / "policy_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
