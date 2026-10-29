import subprocess
import time

print("[*] Starting Automated Test Cases for Deliverable 1...")

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

# Test 1: Query Status
print("\n--- Test 1: Query Initial Resource Utilization ---")
print(run_cmd("python3 client.py h1 STATUS"))

# Test 2: Valid Request
print("\n--- Test 2: Submitting Valid Reservation (200 Mbps for 5s) ---")
print(run_cmd("python3 client.py h1 REQUEST 200 5"))

# Test 3: Concurrent / Conflict Request
print("\n--- Test 3: Submitting Excessive Reservation (900 Mbps) ---")
print(run_cmd("python3 client.py h2 REQUEST 900 10"))

# Test 4: Wait for expiry
print("\n--- Test 4: Waiting 8 seconds for reservation to expire ---")
time.sleep(8)
print(run_cmd("python3 client.py h1 STATUS"))
