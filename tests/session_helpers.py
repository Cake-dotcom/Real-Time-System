"""Provision genuine sender sessions when migrating existing pipeline fixtures."""
from weakref import WeakKeyDictionary

from src.security.source_sessions import authenticate_sender

_senders = WeakKeyDictionary()


def sign_for_monitor(monitor, message):
    source = message["sensor_id"]
    senders = _senders.setdefault(monitor, {})
    if source not in senders:
        senders[source] = authenticate_sender(monitor.sessions, source, monitor.sensor_keys[source])
    try:
        return senders[source].sign(message)
    except ValueError:
        # Non-JSON numeric values are malformed before MAC verification.
        return {**message, "session_id": senders[source].session_id}, "invalid"
