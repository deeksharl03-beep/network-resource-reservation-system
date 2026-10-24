# TCP Server & Reservation Engine - Deeksha

## Modules Handled:
- Multi-threaded TCP Socket Server (`server.py`)
- Reservation protocol handler & resource tracking state machine
- Conflict detection (over-allocation check) & dynamic thread locks
- Expiry manager daemon thread for automated resource release

## Deliverable 1 Verification:
- **TCP Reservation Protocol**: Handles request parsing and JSON responses.
- **Concurrency**: Spawns separate threads for simultaneous client handling.
- **Resource Information & Utilization**: Tracks total, allocated, and free bandwidth.
- **Conflict Detection**: Prevents double-booking and capacity overrun.
- **Reservation Expiry**: Automatically frees up bandwidth after expiration duration.
