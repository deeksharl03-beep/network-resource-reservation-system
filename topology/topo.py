#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

def build():
    net = Mininet(controller=RemoteController, switch=OVSSwitch, link=TCLink)
    net.addController('c0', ip='127.0.0.1', port=6633)

    s = {n: net.addSwitch(n, protocols='OpenFlow13', dpid=f'{i:016x}')
         for i, n in enumerate(['s1', 's2', 's3', 's4'], 1)}
    h = {n: net.addHost(n, ip=f'10.0.0.{i}/24')
         for i, n in enumerate(['h1', 'h2', 'h3', 'h4'], 1)}

    net.addLink(h['h1'], s['s1'], port2=1, bw=100)
    net.addLink(h['h2'], s['s1'], port2=2, bw=100)
    net.addLink(h['h3'], s['s4'], port2=1, bw=100)
    net.addLink(h['h4'], s['s4'], port2=2, bw=100)

    net.addLink(s['s1'], s['s2'], port1=3, port2=1, bw=100)
    net.addLink(s['s2'], s['s4'], port1=2, port2=3, bw=100)
    net.addLink(s['s1'], s['s3'], port1=4, port2=1, bw=50)
    net.addLink(s['s3'], s['s4'], port1=2, port2=4, bw=50)

    net.start()
    net.staticArp()      # avoids ARP loops in the diamond
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    build()
