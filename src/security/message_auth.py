
import hashlib
import hmac
import json


def create_mac(message, secret_key):
    """Generate a MAC for a sensor message."""
    payload = json.dumps(
        message,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hmac.new(
        secret_key.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_message(message, received_mac, secret_key):
    """Verify message authenticity and integrity."""
    expected_mac = create_mac(message, secret_key)

    return hmac.compare_digest(expected_mac, received_mac)


if __name__ == "__main__":
    key = "demo_sensor_secret_key"

    sensor_message = {
        "sensor_id": "LIDAR_01",
        "sequence": 1,
        "timestamp": 1000,
        "distance_m": 12.5,
    }

    mac = create_mac(sensor_message, key)

    print("Original message valid:",
          verify_message(sensor_message, mac, key))

    tampered_message = sensor_message.copy()
    tampered_message["distance_m"] = 2.0

    print("Modified message valid:",
          verify_message(tampered_message, mac, key))
