import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from src.security import source_sessions as protocol
from src.security.message_monitor import MessageMonitor
from src.security import sensor_system as system
from src.security.sensor_features import SensorFeatureTracker
from src.security.sensor_health import SensorHealthMonitor


KEYS = {"LIDAR_01": "test-lidar-secret", "RADAR_01": "test-radar-secret"}


@pytest.fixture
def receiver():
    now = [100.0]
    manager = protocol.SourceSessionManager(KEYS, clock=lambda: now[0], session_ttl=10, challenge_ttl=2)
    return manager, MessageMonitor(KEYS, sessions=manager), now


def sender(manager, source="LIDAR_01"):
    return protocol.authenticate_sender(manager, source, KEYS[source])


def signed(client, sequence=1, reading=12.0):
    return client.sign({"sensor_id": client.source_id, "sequence": sequence,
                        "timestamp": 1000, "distance_m": reading})


def test_first_authentication_and_reuse_metrics(receiver):
    manager, monitor, _ = receiver
    client = sender(manager)
    first = monitor.verify(*signed(client))
    second = monitor.verify(*signed(client, 2))
    assert first["valid"] and second["valid"]
    assert not first["session_reused"] and second["session_reused"]
    assert first["simulated_handshake_cost"] == 2
    assert second["simulated_handshake_cost"] == 0
    assert manager.metrics["full_handshakes"] == 1
    assert manager.metrics["successful_session_reuses"] == 1
    assert manager.metrics["mac_verifications"] == 2
    assert manager.metrics["handshake_processing_ns"] > 0
    assert manager.metrics["message_verification_ns"] > 0


def test_unknown_source_cannot_handshake_or_send(receiver):
    manager, monitor, _ = receiver
    with pytest.raises(protocol.AuthenticationError):
        manager.issue_challenge("unknown")
    assert not monitor.verify({"sensor_id": "unknown"}, "invalid")["valid"]
    assert not manager.sessions


@pytest.mark.parametrize("proof", [None, "bad", [], "\u2603", 1])
def test_invalid_proof_consumes_challenge_without_session(receiver, proof):
    manager, _, _ = receiver
    challenge = manager.issue_challenge("LIDAR_01")
    with pytest.raises(protocol.AuthenticationError):
        manager.complete_handshake("LIDAR_01", challenge["challenge_id"], proof)
    assert not manager.sessions and not manager.pending
    assert manager.metrics["full_handshakes"] == 0


def test_proof_cannot_be_reused_or_moved_between_sources(receiver):
    manager, _, _ = receiver
    challenge = manager.issue_challenge("LIDAR_01")
    proof = protocol.create_source_proof(challenge, KEYS["LIDAR_01"])
    other = manager.issue_challenge("RADAR_01")
    with pytest.raises(protocol.AuthenticationError):
        manager.complete_handshake("RADAR_01", other["challenge_id"], proof)
    manager.complete_handshake("LIDAR_01", challenge["challenge_id"], proof)
    with pytest.raises(protocol.AuthenticationError):
        manager.complete_handshake("LIDAR_01", challenge["challenge_id"], proof)


def test_challenge_expiration(receiver):
    manager, _, now = receiver
    challenge = manager.issue_challenge("LIDAR_01")
    now[0] += 2
    with pytest.raises(protocol.AuthenticationError):
        manager.complete_handshake("LIDAR_01", challenge["challenge_id"],
                                   protocol.create_source_proof(challenge, KEYS["LIDAR_01"]))
    assert not manager.sessions


def test_expiration_reauthentication_and_source_sequence_continuity(receiver):
    manager, monitor, now = receiver
    first = sender(manager)
    assert monitor.verify(*signed(first, 5))["valid"]
    now[0] += 10
    result = monitor.verify(*signed(first, 6))
    assert not result["valid"] and result["reason"] == "Session expired"
    assert not manager.sessions
    second = sender(manager)
    assert second.session_id != first.session_id
    assert not monitor.verify(*signed(second, 5))["valid"]
    assert monitor.verify(*signed(second, 6))["valid"]
    assert manager.metrics["full_handshakes"] == 2


def test_revocation_and_compromise_recovery(receiver):
    manager, monitor, _ = receiver
    first = sender(manager)
    manager.revoke_session("LIDAR_01")
    assert monitor.verify(*signed(first))["reason"] == "Session revoked"
    second = sender(manager)  # Session revocation permits a new proof.
    manager.revoke_source("LIDAR_01")
    assert monitor.verify(*signed(second))["reason"] == "Source revoked"
    with pytest.raises(protocol.AuthenticationError):
        sender(manager)
    manager.reset()
    with pytest.raises(protocol.AuthenticationError):
        sender(manager)
    manager.rotate_source_key("LIDAR_01", "replacement-secret")
    with pytest.raises(protocol.AuthenticationError):
        sender(manager)  # Old provisioned credential is no longer accepted.
    third = protocol.authenticate_sender(manager, "LIDAR_01", "replacement-secret")
    assert monitor.verify(*signed(third))["valid"]


@pytest.mark.parametrize("field,value", [("distance_m", 13.0), ("sensor_id", "RADAR_01"),
                                         ("session_id", "wrong"), ("sequence", 99)])
def test_tampering_rejected_without_replay_state_mutation(receiver, field, value):
    manager, monitor, _ = receiver
    client = sender(manager)
    sender(manager, "RADAR_01")
    message, mac = signed(client)
    message[field] = value
    assert not monitor.verify(message, mac)["valid"]
    assert monitor.last_sequence == {}


def test_old_session_mac_cannot_authenticate_new_session(receiver):
    manager, monitor, _ = receiver
    old = sender(manager)
    message, mac = signed(old)
    new = sender(manager)
    assert not monitor.verify(message, mac)["valid"]
    message["session_id"] = new.session_id
    assert monitor.verify(message, mac)["reason"] == "Invalid MAC"
    assert monitor.verify(*signed(new))["valid"]


def test_sessions_are_isolated_even_with_accidentally_equal_source_secrets():
    keys = {"LIDAR_01": "same", "RADAR_01": "same"}
    manager = protocol.SourceSessionManager(keys)
    a = protocol.authenticate_sender(manager, "LIDAR_01", "same")
    b = protocol.authenticate_sender(manager, "RADAR_01", "same")
    assert a.key != b.key
    message, mac = signed(a)
    message.update(sensor_id="RADAR_01", session_id=b.session_id)
    assert not MessageMonitor(keys, sessions=manager).verify(message, mac)["valid"]


@pytest.mark.parametrize("field,value", [("session_id", None), ("session_id", []),
                                         ("sequence", None), ("sequence", True), ("sequence", -1)])
def test_missing_or_malformed_auth_fields(receiver, field, value):
    manager, monitor, _ = receiver
    client = sender(manager)
    message, _ = signed(client)
    message[field] = value
    mac = protocol.create_session_mac(message, client.key)
    assert not monitor.verify(message, mac)["valid"]
    assert not monitor.last_sequence


def test_reset_and_restart_invalidate_sessions_and_proofs(receiver):
    manager, monitor, _ = receiver
    client = sender(manager)
    challenge = manager.issue_challenge("RADAR_01")
    proof = protocol.create_source_proof(challenge, KEYS["RADAR_01"])
    context = manager.receiver_context
    manager.reset()
    assert manager.receiver_context != context
    assert not monitor.verify(*signed(client))["valid"]
    with pytest.raises(protocol.AuthenticationError):
        manager.complete_handshake("RADAR_01", challenge["challenge_id"], proof)
    fresh = MessageMonitor(KEYS)
    assert not fresh.verify(*signed(client))["valid"]
    new_challenge = fresh.sessions.issue_challenge("RADAR_01")
    with pytest.raises(protocol.AuthenticationError):
        fresh.sessions.complete_handshake("RADAR_01", new_challenge["challenge_id"], proof)


def test_bounded_storage_and_cleanup(receiver):
    _, _, now = receiver
    manager = protocol.SourceSessionManager(KEYS, clock=lambda: now[0],
                                            max_sessions=1, max_challenges=1, session_ttl=1)
    manager.issue_challenge("LIDAR_01")
    with pytest.raises(protocol.AuthenticationError):
        manager.issue_challenge("RADAR_01")
    sender(manager)
    with pytest.raises(protocol.AuthenticationError):
        sender(manager, "RADAR_01")
    assert len(manager.sessions) == 1
    now[0] += 10
    manager.cleanup()
    assert not manager.sessions and not manager.pending
    sender(manager, "RADAR_01")
    assert len(manager.sessions) == 1


def test_handshake_exception_does_not_replace_valid_session(receiver, monkeypatch):
    manager, monitor, _ = receiver
    client = sender(manager)
    challenge = manager.issue_challenge("LIDAR_01")
    proof = protocol.create_source_proof(challenge, KEYS["LIDAR_01"])
    monkeypatch.setattr(protocol, "derive_message_key", Mock(side_effect=RuntimeError("secret material")))
    with pytest.raises(protocol.AuthenticationError, match="^Source authentication failed$"):
        manager.complete_handshake("LIDAR_01", challenge["challenge_id"], proof)
    assert manager.sessions["LIDAR_01"].session_id == client.session_id
    assert monitor.verify(*signed(client))["valid"]


def test_auth_exception_fails_closed_without_history_commit(receiver, monkeypatch):
    manager, monitor, _ = receiver
    client = sender(manager)
    message, mac = signed(client)
    monkeypatch.setattr(system, "message_monitor", monitor)
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    monkeypatch.setattr(system, "health_monitor", SensorHealthMonitor())
    monkeypatch.setattr(manager, "require_session", Mock(side_effect=RuntimeError("secret material")))
    result = system.process_messages([{"message": message, "mac": mac}])["messages"][0]
    assert not result["accepted"] and result["reason"] == "Authentication unavailable"
    assert not system.feature_tracker.history and not system.health_monitor.last_distance
    assert not monitor.last_sequence
    assert "secret material" not in json.dumps(result)


def test_replayed_concurrent_delivery_only_verifies_once(receiver):
    manager, monitor, _ = receiver
    message, mac = signed(sender(manager))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: monitor.verify(message, mac), range(8)))
    assert sum(result["valid"] for result in results) == 1
    assert manager.metrics["replay_rejections"] == 7
    assert manager.metrics["mac_verifications"] == 8


def test_protocol_audit_does_not_expose_credentials(receiver):
    manager, monitor, _ = receiver
    client = sender(manager)
    public = json.dumps({"status": manager.public_status(), "metrics": manager.metrics,
                         "result": monitor.verify(*signed(client))})
    assert client.key not in public and KEYS["LIDAR_01"] not in public
    assert client.key not in repr(client)


def test_handshake_cost_added_once_and_can_cause_deadline_miss(receiver, monkeypatch):
    manager, monitor, _ = receiver
    client = sender(manager)
    monkeypatch.setattr(system, "message_monitor", monitor)
    monkeypatch.setattr(system, "feature_tracker", SensorFeatureTracker())
    monkeypatch.setattr(system, "health_monitor", SensorHealthMonitor())
    def process(sequence):
        message, mac = signed(client, sequence)
        return system.process_messages([{"message": message, "mac": mac, "arrival_time": 0,
            "execution_time": 3, "security_overhead": 1, "deadline": 5}])
    first = process(1)
    assert first["schedule"]["results"][0]["finish"] == 7
    assert first["messages"][0]["status"] == "DEADLINE_MISSED"
    assert not system.feature_tracker.history and not system.health_monitor.last_distance
    second = process(2)
    assert second["schedule"]["results"][0]["finish"] == 5
    assert second["messages"][0]["accepted"]
    assert second["messages"][0]["simulated_handshake_cost"] == 0


def test_expiry_during_mac_verification_fails_closed(receiver, monkeypatch):
    import src.security.message_monitor as module
    manager, monitor, now = receiver
    message, mac = signed(sender(manager))
    original = module.create_session_mac
    def slow_verify(*args):
        now[0] += 10
        return original(*args)
    monkeypatch.setattr(module, "create_session_mac", slow_verify)
    result = monitor.verify(message, mac)
    assert not result["valid"] and result["reason"] == "Session expired"
    assert not monitor.last_sequence


def test_no_downgrade_to_long_term_message_mac(receiver):
    from src.security.message_auth import create_mac
    manager, monitor, _ = receiver
    message, _ = signed(sender(manager))
    assert not monitor.verify(message, create_mac(message, KEYS["LIDAR_01"]))["valid"]
    message.pop("session_id")
    assert not monitor.verify(message, create_mac(message, KEYS["LIDAR_01"]))["valid"]


def test_benchmark_baseline_preserves_replay_security_across_new_sessions():
    from src.ml.benchmark_source_auth import workload, run_once
    messages = workload(30)
    baseline = run_once(messages, "full_auth_every_message")
    reuse = run_once(messages, "session_reuse")
    for report in (baseline, reuse):
        assert report["accepted"] == 30
        assert report["security_violations"] == 0
        assert report["metrics"]["mac_verifications"] == 34
        assert report["metrics"]["replay_rejections"] == 2
    assert baseline["metrics"]["full_handshakes"] == 34
    assert reuse["metrics"]["full_handshakes"] == 3
