
from src.security.message_auth import create_mac, verify_message


class MessageMonitor:
    def __init__(self, sensor_keys):
        self.sensor_keys = sensor_keys
        self.last_sequence = {}

    def verify(self, message, received_mac):
        sensor_id = message.get("sensor_id")

        if sensor_id not in self.sensor_keys:
            return {"valid": False, "reason": "Unknown sensor"}

        if not verify_message(
            message, received_mac, self.sensor_keys[sensor_id]
        ):
            return {"valid": False, "reason": "Invalid MAC"}

        sequence = message.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            return {"valid": False, "reason": "Invalid sequence number"}

        previous = self.last_sequence.get(sensor_id, -1)
        if sequence <= previous:
            return {"valid": False, "reason": "Replay or out-of-order message"}

        self.last_sequence[sensor_id] = sequence
        return {"valid": True, "reason": "Authenticated message"}

        
if __name__ == "__main__":
    key = "demo_lidar_key"
    monitor = MessageMonitor({"LIDAR_01": key})

    message = {
        "sensor_id": "LIDAR_01",
        "sequence": 1,
        "timestamp": 1000,
        "distance_m": 12.5,
    }

    mac = create_mac(message, key)

    print("First delivery:", monitor.verify(message, mac))
    print("Repeated delivery:", monitor.verify(message, mac))
