import threading
import time
import uuid


class ResourceManager:
    def __init__(self, capacity_mbps=100):
        if capacity_mbps <= 0:
            raise ValueError("Capacity must be positive")

        self.capacity_mbps = float(capacity_mbps)
        self.reservations = {}
        self.lock = threading.Lock()

    def _expire_locked(self):
        now = time.monotonic()
        expired = [
            rid for rid, reservation in self.reservations.items()
            if reservation["expires_at"] <= now
        ]

        for rid in expired:
            del self.reservations[rid]

    def reserve(self, client_id, bandwidth_mbps, duration_seconds=300):
        try:
            bandwidth_mbps = float(bandwidth_mbps)
            duration_seconds = float(duration_seconds)
        except (TypeError, ValueError):
            return {
                "accepted": False,
                "message": "Bandwidth and duration must be numbers"
            }

        if bandwidth_mbps <= 0 or duration_seconds <= 0:
            return {
                "accepted": False,
                "message": "Bandwidth and duration must be positive"
            }

        if bandwidth_mbps > self.capacity_mbps:
            return {
                "accepted": False,
                "message": "Request exceeds total capacity"
            }

        with self.lock:
            self._expire_locked()

            used = sum(
                item["bandwidth_mbps"]
                for item in self.reservations.values()
            )
            available = self.capacity_mbps - used

            if bandwidth_mbps > available:
                return {
                    "accepted": False,
                    "message": "Insufficient bandwidth",
                    "available_mbps": round(available, 2)
                }

            rid = str(uuid.uuid4())
            self.reservations[rid] = {
                "client_id": str(client_id),
                "bandwidth_mbps": bandwidth_mbps,
                "expires_at": time.monotonic() + duration_seconds
            }

            return {
                "accepted": True,
                "reservation_id": rid,
                "bandwidth_mbps": bandwidth_mbps,
                "available_mbps": round(
                    available - bandwidth_mbps, 2
                ),
                "message": "Reservation accepted"
            }

    def release(self, reservation_id):
        with self.lock:
            self._expire_locked()
            return self.reservations.pop(reservation_id, None) is not None

    def get_status(self):
        with self.lock:
            self._expire_locked()

            used = sum(
                item["bandwidth_mbps"]
                for item in self.reservations.values()
            )

            return {
                "capacity_mbps": self.capacity_mbps,
                "reserved_mbps": round(used, 2),
                "available_mbps": round(
                    self.capacity_mbps - used, 2
                ),
                "active_reservations": len(self.reservations)
            }
