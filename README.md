
**Computer Networks Project | Problem 15 | Deliverable 1 (D1)**

A TCP reservation service whose accepted requests become OpenFlow policies on an SDN switch.

`TCP sockets` · `Mininet` · `Ryu` · `OpenFlow 1.3`

---

## Overview

Users ask the network for guaranteed bandwidth. A TCP service takes the request, validates it, and the SDN controller installs the matching network policy.

1. **Request** – A client sends a `REQUEST` with bandwidth and duration over TCP.
2. **Validate** – The server checks capacity and conflicts; the controller validates too.
3. **Enforce** – An OpenFlow rule is installed on the switch, and removed on expiry.

## Team

| Member  | Module                                  | Folder    |
|---------|-----------------------------------------|-----------|
| Ved     | Ryu SDN controller + Mininet topology   | `sdn/`    |
| Deeksha | Multi-threaded TCP reservation server   | `server/` |
| Chinmay | TCP client + automated test suite       | `client/` |

## Architecture

```
 Clients (h1, h2, h3)
        │  TCP :8080 (JSON)
        ▼
 Reservation server (h4)  ← threads + lock
        │  UNIX socket: INSTALL / REMOVE
        ▼
 Ryu controller (OpenFlow 1.3)
        │  OpenFlow FlowMod
        ▼
 Switch s1 (Open vSwitch)
```

**Decisions live in the server** (capacity, conflicts, expiry). **Enforcement lives in the controller**, which programs the switch.

## Features

| Expectation | What we built | Phase |
|---|---|---|
| TCP reservation protocol | JSON `REQUEST` / `STATUS` over TCP port 8080 | D1 |
| Concurrent requests | One thread per client + shared lock | D1 |
| Maintain resource info | Total / allocated / available bandwidth table | D1 |
| Detect conflicts | Capacity overrun and duplicate reservation | D1 |
| Install SDN policies | Ryu pushes a flow rule on `ACCEPT` | D1 (base) |
| Reservation expiry | Daemon thread frees bandwidth and removes rule | D1 |
| Track utilization | `STATUS` reports utilization % | D1 |
| Evaluate accepted / rejected | Statistics and comparison | D2 |

## How It Works

### TCP reservation service
- **Protocol:** The client sends JSON containing `action`, `client_id`, `bandwidth` and `duration`. The server replies `ACCEPTED`, `REJECTED` or a `STATUS` report.
- **Concurrency:** Each connection runs in its own thread. A lock guards the shared reservation table.
- **Resources:** 1000 Mbps total. Tracks allocated, available and utilization %. One active reservation per client.
- **Conflict detection:** Rejects when the request exceeds free capacity, or the client already holds a reservation.
- **Expiry:** A background thread checks every 2 s, frees the bandwidth and tells the controller to remove the rule.

### Mininet topology and Ryu controller
- **Mininet:** One OpenFlow 1.3 switch `s1` and four hosts. `h1`–`h3` are clients, `h4` runs the reservation server. Remote controller at `127.0.0.1:6653`.
- **Ryu controller:** Handshakes with the switch, installs a table-miss rule to the controller, and handles `PacketIn` as a flood hub so every host can reach `h4`.
- **Result:** `pingall` shows 0% dropped (12/12), so clients reach the server through the SDN switch.

### Socket–SDN integration
1. **Server accepts** – Capacity and conflict checks pass, then the server sends `INSTALL (client, bandwidth)` to the controller (UNIX socket `/tmp/sdn_controller.sock`).
2. **Controller installs** – Validates the request, then pushes a priority-100 flow rule matching the client IP, tagged with a cookie.
3. **Expiry removes** – The server sends `REMOVE`; the controller deletes the rule by its cookie and the bandwidth is freed.

If the controller refuses or is unreachable, the request is `REJECTED`, so the table never promises what the network did not install.

## Getting Started

### Prerequisites
- Linux VM with [Mininet](http://mininet.org/) and Open vSwitch
- Python 3 with [Ryu](https://ryu-sdn.org/) (e.g. in a virtualenv `~/ryu-env`)

### Run

Put all files (`sdn_controller.py`, `topology.py`, `server.py`, `client.py`, `test_suite.py`) in one folder, e.g. `~/project`, and run everything from there.

**Setup (once)**
```bash
mkdir -p ~/project && cd ~/project
unzip -o ~/Downloads/d1.zip
```

**Terminal 1 – Ryu controller**
```bash
cd ~/project
source ~/ryu-env/bin/activate
ryu-manager sdn_controller.py
```
Wait for `Policy channel listening on /tmp/sdn_controller.sock`.

**Terminal 2 – Mininet topology**
```bash
cd ~/project
sudo mn -c
sudo python3 topology.py
```

**At the `mininet>` prompt**
```
pingall
h4 python3 server.py &
```

Run the automated test suite from h1:
```
h1 python3 test_suite.py
```

Or try the manual flow-table demo:
```
h1 python3 client.py h1 REQUEST 200 30
sh ovs-ofctl -O OpenFlow13 dump-flows s1
h2 python3 client.py h2 REQUEST 900 10
h1 python3 client.py h1 STATUS
```
- The `dump-flows` output shows a `priority=100` rule for `10.0.0.1`.
- The 900 Mbps request is `REJECTED` (only 800 Mbps free).
- After about 30 s, h1's reservation expires and the rule is removed (check with `dump-flows` again).

## Demo Results (D1)

| Test | Scenario | Outcome |
|---|---|---|
| 1 | Initial `STATUS` | 1000 Mbps available, 0% utilization, 0 active reservations |
| 2 | Valid request: 200 Mbps for 5 s (h1) | `ACCEPTED`, `sdn_policy: INSTALLED`, utilization 200/1000 Mbps |
| 3 | Excessive request: 900 Mbps (h2) | `REJECTED` – capacity exceeded (requested 900, available 800) |
| 4 | Wait 8 s, then `STATUS` | Reservation expired, bandwidth freed (0% used) |

Controller log during the run shows the policy lifecycle:
```
[SDN Controller] INSTALLED policy for h1 (10.0.0.1): 200 Mbps, cookie=1, priority=100
[SDN Controller] REMOVED policy for h1 (cookie=1)
```

## Roadmap

### D1 – Done
- Users can ask for bandwidth over TCP
- Server accepts or rejects the request (not enough bandwidth, or already reserved)
- Reservation ends by itself after its time
- Controller adds a rule on the switch when accepted, and removes it when expired
- Everything tested in Mininet

### D2 – Planned
- Really limit the speed to the reserved amount
- Bigger network with more switches
- Test with many users at the same time
- Compare accepted and rejected requests and show the results

## Repository Structure

```
.
├── sdn_controller.py   # Ryu controller (Ved)
├── topology.py         # Mininet topology (Ved)
├── server.py           # Multi-threaded TCP reservation server (Deeksha)
├── client.py           # TCP client (Chinmay)
├── test_suite.py       # Automated test suite (Chinmay)
└── README.md
```
