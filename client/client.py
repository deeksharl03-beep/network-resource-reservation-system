import socket
import json
import sys

SERVER_HOST = '10.0.0.4'  # h4 = reservation server in Mininet (use 127.0.0.1 for local test)
SERVER_PORT = 8080

def send_request(payload):
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client.connect((SERVER_HOST, SERVER_PORT))
        client.sendall(json.dumps(payload).encode('utf-8'))
        
        response_data = client.recv(2048).decode('utf-8')
        client.close()
        return json.loads(response_data)
    except Exception as e:
        return {"status": "ERROR", "reason": f"Connection failed: {str(e)}"}

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 client.py <client_id> <REQUEST/STATUS> [bandwidth_mbps] [duration_sec]")
        print("Example 1 (Request): python3 client.py h1 REQUEST 250 15")
        print("Example 2 (Status):  python3 client.py h1 STATUS")
        sys.exit(1)

    client_id = sys.argv[1]
    action = sys.argv[2].upper()

    payload = {"client_id": client_id, "action": action}

    if action == "REQUEST":
        if len(sys.argv) < 5:
            print("[!] Error: Bandwidth and Duration parameters required for REQUEST.")
            sys.exit(1)
        payload["bandwidth"] = int(sys.argv[3])
        payload["duration"] = int(sys.argv[4])

    print(f"[*] Sending {action} payload for {client_id} to server {SERVER_HOST}:{SERVER_PORT}...")
    response = send_request(payload)
    print("\n================ SERVER RESPONSE ================")
    print(json.dumps(response, indent=4))
    print("=================================================\n")

if __name__ == "__main__":
    main()
