# network-resource-reservation-system
SDN-based Network Resource Reservation System using TCP and OpenFlow
# Network Resource Reservation System (SDN + TCP Sockets)

Jackfruit Mini Project, Problem 15. Deliverable 1.

Users request network bandwidth over a TCP reservation protocol. The server validates requests,
detects conflicts, tracks utilization and expires reservations. An OpenFlow 1.3 (Ryu) controller
runs the Mininet network the application runs on.

## Team
| Member | Module | Folder |
|---|---|---|
| Ved | Ryu SDN controller + Mininet topology | `sdn/` |
| Deeksha | Multi-threaded TCP reservation server | `server/` |
| Chinmay | TCP client + automated test suite | `client/` |

## Architecture
```
 h1, h2, h3 (clients)  --TCP:8080-->  s1 (OVS, OpenFlow 1.3)  -->  h4 (reservation server)
                                         |
                                  Ryu controller (127.0.0.1:6653)
```
- Total capacity: 1000 Mbps. Requests that exceed free capacity are REJECTED.
- A client can hold one active reservation; duplicates are REJECTED.
- Reservations expire automatically and free their bandwidth.
- Protocol: JSON messages over TCP (`REQUEST`, `STATUS`).

## Requirements
Ubuntu 22.04, Mininet, Open vSwitch, Python 3.9 virtualenv with Ryu 4.34 + eventlet 0.30.2.

## How to run
Copy all `.py` files into one folder (they run from the same directory):
```
mkdir -p ~/run
find . -name "*.py" -exec cp {} ~/run/ \;
cd ~/run
```
Order matters: clean up first, then controller, then Mininet.

1. Terminal 2: `sudo mn -c`
2. Terminal 1 (Ryu environment active): `ryu-manager sdn_controller.py`
3. Terminal 2: `sudo python3 topology.py`
4. At `mininet>`:
```
pingall
h4 python3 server.py &
h1 python3 client.py h1 STATUS
h1 python3 client.py h1 REQUEST 200 5
h2 python3 client.py h2 REQUEST 900 10
h1 python3 client.py h1 REQUEST 100 5
h3 python3 client.py h3 REQUEST 300 20
h1 python3 test_suite.py
```

## Test cases
| Test | Expected |
|---|---|
| `pingall` | 0% dropped |
| h1 requests 200 Mbps | ACCEPTED |
| h2 requests 900 Mbps | REJECTED (capacity) |
| h1 requests again | REJECTED (duplicate) |
| h3 requests 300 Mbps | ACCEPTED |
| STATUS after expiry | allocated returns to 0 |

## Screenshots
Add real screenshots of the run in `screenshots/`.

## Known limitations (planned for Deliverable 2)
The server does not yet send reservations to the controller, so flow rules and meters are not
installed per reservation. The controller currently floods packets. D2 adds server-to-controller
integration, dynamic policies, and performance evaluation against a static baseline.
