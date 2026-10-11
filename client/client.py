import json
import socket
import argparse

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000


def send_request(request):
    with socket.create_connection(
        (SERVER_HOST, SERVER_PORT), timeout=5
    ) as connection:
        with connection.makefile("rwb") as stream:
            message = json.dumps(request).encode("utf-8") + b"\n"
            stream.write(message)
            stream.flush()

            response = stream.readline()

            if not response:
                raise ConnectionError("Server closed the connection")

            return json.loads(response.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Network bandwidth reservation client"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    reserve_parser = subparsers.add_parser("reserve")
    reserve_parser.add_argument("--client", required=True)
    reserve_parser.add_argument("--bandwidth", type=float, required=True)
    reserve_parser.add_argument("--duration", type=float, default=300)

    subparsers.add_parser("status")

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--id", required=True)

    args = parser.parse_args()

    if args.action == "reserve":
        request = {
            "action": "reserve",
            "client_id": args.client,
            "bandwidth_mbps": args.bandwidth,
            "duration_seconds": args.duration
        }
    elif args.action == "status":
        request = {"action": "status"}
    else:
        request = {
            "action": "release",
            "reservation_id": args.id
        }

    try:
        response = send_request(request)
        print(json.dumps(response, indent=2))
    except (OSError, ValueError) as error:
        print(f"Request failed: {error}")


if __name__ == "__main__":
    main()
