"""Prototype PSK challenge-response sessions; no secrets in public audit output.

Single active session and pending challenge per provisioned identity. Locks make
proof consumption, session replacement and message verification atomic. A fresh
receiver context invalidates every pre-reset transcript. This is not a standard
automotive key-management protocol and provides no forward secrecy.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import secrets
import threading
import time


PROTOCOL = "sensor-source-v1"
SESSION_TTL_SECONDS = 60.0
CHALLENGE_TTL_SECONDS = 5.0
SIMULATED_HANDSHAKE_COST = 2.0


class AuthenticationError(ValueError):
    """Contains only a fixed public reason, never supplied credentials."""


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def keyed_tag(secret, purpose, value):
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(key, canonical_bytes({"protocol": PROTOCOL, "purpose": purpose,
                                        "value": value}), hashlib.sha256).hexdigest()


def create_source_proof(challenge, source_secret):
    return keyed_tag(source_secret, "source-proof", challenge)


def derive_message_key(challenge, session_id, source_secret):
    return keyed_tag(source_secret, "message-key", {"challenge": challenge,
                                                   "session_id": session_id})


def create_session_mac(message, session_key):
    return keyed_tag(session_key, "sensor-message", message)


@dataclass
class Session:
    source_id: str
    session_id: str
    expires_at: float
    key: str = field(repr=False)
    verified_messages: int = 0


@dataclass
class SenderSession:
    """Sender-side credentials. Never include this object in logs or UI state views."""
    source_id: str
    session_id: str
    key: str = field(repr=False)

    def sign(self, message):
        if message.get("sensor_id") != self.source_id:
            raise AuthenticationError("Sender identity mismatch")
        bound = {**message, "session_id": self.session_id}
        return bound, create_session_mac(bound, self.key)


class SourceSessionManager:
    def __init__(self, sensor_keys, *, clock=time.monotonic, session_ttl=SESSION_TTL_SECONDS,
                 challenge_ttl=CHALLENGE_TTL_SECONDS, max_sessions=64, max_challenges=64,
                 revoked_sources=()):
        if (not math.isfinite(session_ttl) or session_ttl <= 0
                or not math.isfinite(challenge_ttl) or challenge_ttl <= 0
                or max_sessions < 1 or max_challenges < 1):
            raise ValueError("Invalid session configuration")
        self.sensor_keys = dict(sensor_keys)
        self.clock = clock
        self.session_ttl = session_ttl
        self.challenge_ttl = challenge_ttl
        self.max_sessions = max_sessions
        self.max_challenges = max_challenges
        self.lock = threading.RLock()
        self.sessions = {}
        self.pending = {}
        self.last_state = {}  # At most one non-secret tombstone per provisioned source.
        self.revoked_sources = set(revoked_sources) & self.sensor_keys.keys()
        self.last_sequence = {}  # Per source, retained across expiration/reauthentication.
        self.receiver_context = secrets.token_hex(32)
        self.metrics = dict.fromkeys(("handshake_attempts", "full_handshakes",
            "successful_session_reuses", "failed_authentications", "mac_verifications",
            "replay_rejections", "handshake_processing_ns", "message_verification_ns"), 0)

    def now(self):
        value = self.clock()
        if not math.isfinite(value):
            raise AuthenticationError("Authentication clock unavailable")
        return value

    def _identity(self, source_id):
        if not isinstance(source_id, str) or source_id not in self.sensor_keys:
            raise AuthenticationError("Unknown source")
        if source_id in self.revoked_sources:
            raise AuthenticationError("Source revoked")

    def cleanup(self):
        with self.lock:
            now = self.now()
            for source, (_, expiry) in list(self.pending.items()):
                if now >= expiry:
                    del self.pending[source]
            for source, session in list(self.sessions.items()):
                if now >= session.expires_at:
                    self.last_state[source] = (session.session_id, "expired")
                    del self.sessions[source]

    def issue_challenge(self, source_id):
        started = time.perf_counter_ns()
        with self.lock:
            self.metrics["handshake_attempts"] += 1
            try:
                self._identity(source_id)
                self.cleanup()
                if source_id not in self.pending and len(self.pending) >= self.max_challenges:
                    raise AuthenticationError("Challenge capacity reached")
                challenge = {"source_id": source_id, "receiver_context": self.receiver_context,
                             "challenge_id": secrets.token_hex(16), "nonce": secrets.token_hex(32)}
                self.pending[source_id] = (challenge, self.now() + self.challenge_ttl)
                return dict(challenge)
            except Exception:
                self.metrics["failed_authentications"] += 1
                raise AuthenticationError("Challenge unavailable") from None
            finally:
                self.metrics["handshake_processing_ns"] += time.perf_counter_ns() - started

    def complete_handshake(self, source_id, challenge_id, proof):
        started = time.perf_counter_ns()
        with self.lock:
            try:
                self._identity(source_id)
                # Consume a challenge on ANY completion attempt, including exceptions.
                pending = self.pending.pop(source_id, None)
                if pending is None:
                    raise AuthenticationError("Challenge unavailable")
                challenge, expiry = pending
                if (self.now() >= expiry or challenge_id != challenge["challenge_id"]
                        or not isinstance(proof, str)
                        or not hmac.compare_digest(create_source_proof(challenge, self.sensor_keys[source_id]), proof)):
                    raise AuthenticationError("Invalid source proof")
                self.cleanup()
                if source_id not in self.sessions and len(self.sessions) >= self.max_sessions:
                    raise AuthenticationError("Session capacity reached")
                session_id = secrets.token_hex(32)
                key = derive_message_key(challenge, session_id, self.sensor_keys[source_id])
                expires_at = self.now() + self.session_ttl
                session = Session(source_id, session_id, expires_at, key)
                # Commit only after proof, key derivation and clock operations succeed.
                self.sessions[source_id] = session
                self.last_state.pop(source_id, None)
                self.metrics["full_handshakes"] += 1
                return {"source_id": source_id, "session_id": session_id,
                        "expires_at_monotonic": expires_at}
            except Exception:
                self.metrics["failed_authentications"] += 1
                raise AuthenticationError("Source authentication failed") from None
            finally:
                self.metrics["handshake_processing_ns"] += time.perf_counter_ns() - started

    def require_session(self, source_id, session_id):
        self._identity(source_id)
        if not isinstance(session_id, str) or not session_id:
            raise AuthenticationError("Missing or malformed session identifier")
        self.cleanup()
        session = self.sessions.get(source_id)
        if session is None or session.session_id != session_id:
            previous = self.last_state.get(source_id)
            if previous and previous[0] == session_id:
                raise AuthenticationError(f"Session {previous[1]}")
            raise AuthenticationError("Unknown or wrong session identifier")
        return session

    def revoke_session(self, source_id):
        with self.lock:
            session = self.sessions.pop(source_id, None)
            self.pending.pop(source_id, None)
            if session:
                self.last_state[source_id] = (session.session_id, "revoked")

    def revoke_source(self, source_id):
        """Administrative compromise response; not triggered by unauthenticated traffic."""
        with self.lock:
            if isinstance(source_id, str) and source_id in self.sensor_keys:
                self.revoke_session(source_id)
                self.revoked_sources.add(source_id)

    def rotate_source_key(self, source_id, new_secret):
        """Trusted administrative recovery, requiring a new provisioned secret."""
        with self.lock:
            if (source_id not in self.sensor_keys or not isinstance(new_secret, str)
                    or not new_secret or new_secret == self.sensor_keys[source_id]):
                raise ValueError("A new source secret is required")
            self.revoke_session(source_id)
            self.sensor_keys[source_id] = new_secret
            self.revoked_sources.discard(source_id)

    def reset(self):
        with self.lock:
            new_context = secrets.token_hex(32)
            self.sessions.clear()
            self.pending.clear()
            self.last_state.clear()
            self.last_sequence.clear()
            self.receiver_context = new_context
            # Administrative source revocations survive a simulation reset.

    def public_status(self):
        with self.lock:
            self.cleanup()
            now = self.now()
            return [{"source_id": source, "state": (
                        "revoked" if source in self.revoked_sources else
                        "active" if source in self.sessions else
                        self.last_state.get(source, (None, "unauthenticated"))[1]),
                     "expires_in_seconds": max(0, self.sessions[source].expires_at - now)
                        if source in self.sessions else None,
                     "verified_messages": self.sessions[source].verified_messages
                        if source in self.sessions else 0}
                    for source in self.sensor_keys]


def authenticate_sender(manager, source_id, source_secret):
    """Simulated sensor-side exchange. The receiver never invents the sender proof."""
    challenge = manager.issue_challenge(source_id)
    proof = create_source_proof(challenge, source_secret)
    grant = manager.complete_handshake(source_id, challenge["challenge_id"], proof)
    return SenderSession(source_id, grant["session_id"],
                         derive_message_key(challenge, grant["session_id"], source_secret))
