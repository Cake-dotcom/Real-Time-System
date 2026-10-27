"""Mandatory source session, per-message integrity, and replay verification."""
import hmac
import time

from src.security.source_sessions import (
    AuthenticationError, SourceSessionManager, create_session_mac,
    SIMULATED_HANDSHAKE_COST,
)


class MessageMonitor:
    def __init__(self, sensor_keys, *, sessions=None):
        self.sessions = sessions if sessions is not None else SourceSessionManager(sensor_keys)
        self.sensor_keys = self.sessions.sensor_keys
        self.last_sequence = self.sessions.last_sequence

    def verify(self, message, received_mac):
        started = time.perf_counter_ns()
        with self.sessions.lock:
            result = {"valid": False, "reason": "Authentication unavailable",
                      "authentication": "not_evaluated", "source_authentication": "not_evaluated",
                      "replay": "not_evaluated", "session_reused": False,
                      "simulated_handshake_cost": 0.0}
            try:
                self._verify(message, received_mac, result)
            except AuthenticationError as error:
                result["reason"] = str(error)  # Only fixed public protocol reasons.
                result["source_authentication"] = "failed"
            except Exception:
                # Do not expose exceptions that could include credentials or payloads.
                result["reason"] = "Authentication unavailable"
            if not result["valid"]:
                self.sessions.metrics["failed_authentications"] += 1
            elapsed = time.perf_counter_ns() - started
            self.sessions.metrics["message_verification_ns"] += elapsed
            result["measured_verification_ns"] = elapsed
            return result

    def _verify(self, message, received_mac, result):
        if not isinstance(message, dict):
            result["reason"] = "Malformed message"
            return
        source = message.get("sensor_id")
        if not isinstance(source, str) or source not in self.sensor_keys:
            result.update(reason="Unknown sensor", source_authentication="failed")
            return
        session = self.sessions.require_session(source, message.get("session_id"))
        result["source_authentication"] = "passed"
        self.sessions.metrics["mac_verifications"] += 1
        try:
            valid = isinstance(received_mac, str) and hmac.compare_digest(
                create_session_mac(message, session.key), received_mac)
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            result.update(reason="Invalid MAC", authentication="failed")
            return
        result["authentication"] = "passed"
        sequence = message.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            result.update(reason="Invalid sequence number", replay="failed")
            return
        if sequence <= self.last_sequence.get(source, -1):
            self.sessions.metrics["replay_rejections"] += 1
            result.update(reason="Replay or out-of-order message", replay="failed")
            return
        if self.sessions.now() >= session.expires_at:
            raise AuthenticationError("Session expired")
        # No trust-state mutation until source, MAC and replay checks all succeed.
        reused = session.verified_messages > 0
        self.last_sequence[source] = sequence
        session.verified_messages += 1
        if reused:
            self.sessions.metrics["successful_session_reuses"] += 1
        result.update(valid=True, reason="Authenticated message", replay="passed",
                      session_reused=reused,
                      simulated_handshake_cost=0.0 if reused else SIMULATED_HANDSHAKE_COST)
