from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info

def create_topology():
    net = Mininet(controller=RemoteController, switch=OVSKernelSwitch)

    info("*** Adding SDN Controller\n")
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    info("*** Adding OpenFlow Switch\n")
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    info("*** Adding Hosts (Reservation Clients)\n")
    h1 = net.addHost('h1', ip='10.0.0.1')
    h2 = net.addHost('h2', ip='10.0.0.2')
    h3 = net.addHost('h3', ip='10.0.0.3')
    h4 = net.addHost('h4', ip='10.0.0.4')  # Reservation SERVER

    info("*** Creating Network Links\n")
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)

    info("*** Starting Network & Connecting to Controller\n")
    net.start()
    
    info("*** Running Mininet CLI\n")
    CLI(net)

    info("*** Stopping Network\n")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    create_topology()
