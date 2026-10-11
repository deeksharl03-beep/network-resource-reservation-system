import json
import socket

HOST = "127.0.0.1"
PORT = 9000


def send_request(request):
    """Send a JSON request to the reservation server over TCP."""
    try:
        with socket.create_connection((HOST, PORT), timeout=5) as sock:
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            file = sock.makefile("r", encoding="utf-8")
            response = file.readline()
            file.close()

            if not response:
                return {"success": False, "message": "Empty server response"}

            return json.loads(response)

    except (OSError, json.JSONDecodeError) as error:
        return {
            "success": False,
            "message": str(error)
        }


if __name__ == "__main__":
    result = send_request({"action": "status"})
    print(json.dumps(result, indent=2))
