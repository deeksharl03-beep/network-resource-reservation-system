import socket
import threading
import time
import json
import os

HOST = '0.0.0.0'
PORT = int(os.environ.get("RESERVATION_PORT", 8080))
TOTAL_BANDWIDTH = 1000  # Total available bandwidth in Mbps

# Socket-SDN integration: channel to the Ryu controller (see sdn_controller.py)
SDN_SOCKET_PATH = os.environ.get("SDN_SOCKET_PATH", "/tmp/sdn_controller.sock")

# Shared state variables
allocated_bandwidth = 0
reservations = {}  # {client_id: {"bandwidth": val, "expiry": time_val}}
lock = threading.Lock()


def notify_controller(message):
    """Send one policy command to the SDN controller and return its JSON reply."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect(SDN_SOCKET_PATH)
        s.sendall((json.dumps(message) + "\n").encode('utf-8'))
        reply = json.loads(s.recv(4096).decode('utf-8'))
        s.close()
        return reply
    except Exception as e:
        return {"status": "ERROR", "reason": f"Controller unreachable: {e}"}


def cleanup_reservations():
    """Background thread to detect and handle reservation expiration automatically."""
    global allocated_bandwidth
    while True:
        time.sleep(2)
        current_time = time.time()
        expired = []
        with lock:
            for client_id, res in list(reservations.items()):
                if current_time > res["expiry"]:
                    allocated_bandwidth -= res["bandwidth"]
                    expired.append((client_id, res["bandwidth"]))
                    del reservations[client_id]

        # Tell the controller to remove the flow rules (outside the lock)
        for client_id, bw in expired:
            reply = notify_controller({"cmd": "REMOVE", "client_id": client_id})
            print(f"[-] Reservation expired for {client_id}. Freed {bw} Mbps. "
                  f"[SDN_POLICY] remove -> {reply.get('status')}")


def handle_client(conn, addr):
    global allocated_bandwidth
    print(f"[+] Connected to client: {addr}")
    try:
        data = conn.recv(1024).decode('utf-8')
        if not data:
            return

        request = json.loads(data)
        action = request.get("action")
        client_id = request.get("client_id")
        requested_bw = request.get("bandwidth", 0)
        duration = request.get("duration", 10)  # seconds

        if action == "REQUEST" and (not client_id or not isinstance(requested_bw, int)
                or not isinstance(duration, int) or requested_bw <= 0 or duration <= 0):
            conn.sendall(json.dumps({"status": "ERROR",
                "reason": "client_id required; bandwidth and duration must be positive integers"}).encode('utf-8'))
            return

        with lock:
            if action == "REQUEST":
                # Conflict detection & Capacity check
                if client_id in reservations:
                    response = {
                        "status": "REJECTED",
                        "reason": f"Active reservation already exists for client {client_id}"
                    }
                elif allocated_bandwidth + requested_bw > TOTAL_BANDWIDTH:
                    response = {
                        "status": "REJECTED",
                        "reason": f"Conflict/Capacity Limit Exceeded. Requested: {requested_bw} Mbps, Available: {TOTAL_BANDWIDTH - allocated_bandwidth} Mbps"
                    }
                else:
                    # Socket-SDN integration: ask the controller to install the policy.
                    # Kept inside the lock so two clients cannot over-book in between.
                    sdn_reply = notify_controller({"cmd": "INSTALL", "client_id": client_id,
                                                   "bandwidth": requested_bw})
                    if sdn_reply.get("status") != "OK":
                        response = {
                            "status": "REJECTED",
                            "reason": f"SDN policy install failed: {sdn_reply.get('reason')}"
                        }
                    else:
                        expiry_time = time.time() + duration
                        reservations[client_id] = {"bandwidth": requested_bw, "expiry": expiry_time}
                        allocated_bandwidth += requested_bw
                        response = {
                            "status": "ACCEPTED",
                            "allocated_bandwidth": requested_bw,
                            "expires_in": duration,
                            "current_utilization": f"{allocated_bandwidth}/{TOTAL_BANDWIDTH} Mbps",
                            "sdn_policy": "INSTALLED"
                        }
                        print(f"[SDN_POLICY] Request accepted for {client_id}: {requested_bw} Mbps for {duration}s -> controller INSTALLED")

            elif action == "STATUS":
                response = {
                    "total_bandwidth": TOTAL_BANDWIDTH,
                    "allocated_bandwidth": allocated_bandwidth,
                    "available_bandwidth": TOTAL_BANDWIDTH - allocated_bandwidth,
                    "utilization_percentage": round((allocated_bandwidth / TOTAL_BANDWIDTH) * 100, 2),
                    "active_reservations": len(reservations)
                }
            else:
                response = {"status": "ERROR", "reason": "Invalid action requested"}

        conn.sendall(json.dumps(response).encode('utf-8'))
    except Exception as e:
        print(f"[!] Error handling client {addr}: {e}")
    finally:
        conn.close()


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    print(f"[*] TCP Reservation Server running on {HOST}:{PORT}")

    # Daemon thread to handle automated expiry
    threading.Thread(target=cleanup_reservations, daemon=True).start()

    while True:
        conn, addr = server.accept()
        # Handle each client connection in a separate thread for concurrency
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()
