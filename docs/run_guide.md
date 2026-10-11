# Run guide (Ved: network and SDN)

## Start order (always)
1. Ryu controller  2. Mininet  3. Reservation server  4. Client / monitor

## Tab 1: Ryu
    sudo mn -c
    sudo service openvswitch-switch restart
    cd ~/network-reservation/controller
    source ~/ryu-env/bin/activate
    ryu-manager reservation_ryu.py
Wait for: wsgi starting up on http://0.0.0.0:8080

## Tab 2: Mininet (no venv)
    cd ~/network-reservation/topology
    sudo python3 topo.py
Ryu prints "Switch connected" for switches 1 to 4. Then run: pingall (expect 0% dropped).

## Tab 3: checks
    curl http://127.0.0.1:8080/switches
    curl http://127.0.0.1:8080/policy
    curl http://127.0.0.1:8080/stats/ports
    sudo ovs-ofctl -O OpenFlow13 dump-flows s1
    sudo ovs-ofctl -O OpenFlow13 dump-meters s1

## Enforcement test
    mininet> h3 iperf -s &
    mininet> h1 iperf -c 10.0.0.3 -t 10        (baseline)
    curl -X POST http://127.0.0.1:8080/policy -H "Content-Type: application/json" -d @policy_good.json
    mininet> h1 iperf -c 10.0.0.3 -t 10        (about 20 Mbps)
    curl -X DELETE http://127.0.0.1:8080/policy/1
Measured on my VM: 80.7 -> 21.9 -> 71.5 Mbits/sec.

## Validation test
    ./test_policy.sh     (expect 200, 409, 400, 409, 400, list, 200, 404)

## Shutdown
    mininet> exit        then Ctrl+C in the Ryu tab, then: sudo mn -c

## Notes
- Do not restart Ryu while Mininet is running; restart both, Ryu first.
- Meters limit the forward direction (src to dst) only.
- Mininet runs with system python3; Ryu runs inside ~/ryu-env.
