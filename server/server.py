import socket
import threading
import time
import json

HOST = '0.0.0.0'
PORT = 8080
TOTAL_BANDWIDTH = 1000  # Total available bandwidth in Mbps

# Shared state variables
allocated_bandwidth = 0
reservations = {}  # {client_id: {"bandwidth": val, "expiry": time_val}}
lock = threading.Lock()

def cleanup_reservations():
    """Background thread to detect and handle reservation expiration automatically."""
    global allocated_bandwidth
    while True:
        time.sleep(2)
        current_time = time.time()
        with lock:
            expired_clients = []
            for client_id, res in reservations.items():
                if current_time > res["expiry"]:
                    expired_clients.append(client_id)
            
            for client_id in expired_clients:
                allocated_bandwidth -= reservations[client_id]["bandwidth"]
                print(f"[-] Reservation expired for {client_id}. Freed {reservations[client_id]['bandwidth']} Mbps.")
                del reservations[client_id]

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
                    expiry_time = time.time() + duration
                    reservations[client_id] = {"bandwidth": requested_bw, "expiry": expiry_time}
                    allocated_bandwidth += requested_bw
                    response = {
                        "status": "ACCEPTED", 
                        "allocated_bandwidth": requested_bw, 
                        "expires_in": duration,
                        "current_utilization": f"{allocated_bandwidth}/{TOTAL_BANDWIDTH} Mbps"
                    }
                    print(f"[SDN_POLICY] Request accepted for {client_id}: {requested_bw} Mbps for {duration}s")

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
