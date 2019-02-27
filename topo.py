from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel

class MyTopo( Topo ):
    "Simple topology example."

    def __init__( self ):
        "Create custom topo."

        # Initialize topology
        Topo.__init__( self )

        hosts = []
        switches = []

        # Add hosts and switches
        hosts.append(self.addHost( 'h1'))
        hosts.append(self.addHost( 'h2' ))
        hosts.append(self.addHost( 'h3' ))
        hosts.append(self.addHost( 'h4' ))

        switches.append(self.addSwitch( 's1' ))
        # switches.append(self.addSwitch( 's2' ))

        # Add links
        self.addLink(hosts[0], switches[0], delay='10ms', max_queue_size=1000)
        self.addLink(hosts[1], switches[0], delay='10ms', max_queue_size=1000)
        self.addLink(hosts[2], switches[0], delay='10ms', max_queue_size=1000)
        self.addLink(hosts[3], switches[0], delay='10ms', max_queue_size=1000)

        # self.addLink(switches[0], switches[1], cls=TCLink, delay='40ms', max_queue_size=1000)

        # self.addLink(hosts[2], switches[1], cls=TCLink, delay='40ms', max_queue_size=1000)
        # self.addLink(hosts[3], switches[0], cls=TCLink, delay='40ms', max_queue_size=1000)

topos = { 'mytopo': ( lambda: MyTopo() ) }