import json
import socketserver

from server.resource import ResourceManager

HOST = "0.0.0.0"
PORT = 9000

manager = ResourceManager(capacity_mbps=100)


class ReservationHandler(socketserver.StreamRequestHandler):
    def handle(self):
        print(f"Client connected: {self.client_address[0]}")

        for raw_line in self.rfile:
            try:
                request = json.loads(raw_line.decode("utf-8"))

                if not isinstance(request, dict):
                    raise ValueError("Request must be a JSON object")

                action = request.get("action")

                if action == "reserve":
                    response = manager.reserve(
                        client_id=request.get("client_id", "anonymous"),
                        bandwidth_mbps=request.get("bandwidth_mbps"),
                        duration_seconds=request.get("duration_seconds", 300)
                    )

                elif action == "status":
                    response = {
                        "success": True,
                        **manager.get_status()
                    }

                elif action == "release":
                    reservation_id = request.get("reservation_id")

                    if not isinstance(reservation_id, str):
                        response = {
                            "success": False,
                            "message": "reservation_id must be a string"
                        }
                    else:
                        released = manager.release(reservation_id)
                        response = {
                            "success": released,
                            "message": "Reservation released" if released
                            else "Reservation not found or expired"
                        }

                else:
                    response = {
                        "success": False,
                        "message": "Unknown action"
                    }

            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                response = {
                    "success": False,
                    "message": "Invalid request"
                }

            self.wfile.write(
                (json.dumps(response) + "\n").encode("utf-8")
            )
            self.wfile.flush()
            print("Response:", response)


class ReservationServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ReservationServer((HOST, PORT), ReservationHandler) as server:
        print(f"Reservation server listening on {HOST}:{PORT}")
        print("Waiting for TCP clients...")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
