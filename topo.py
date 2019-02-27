from mininet.topo import Topo
from mininet.link import TCLink

class MyTopo( Topo ):
    "Simple topology example."

    def __init__( self ):
        "Create custom topo."

        # Initialize topology
        Topo.__init__( self )

        hosts = []
        switches = []

        # Add hosts and switches
        hosts.append(self.addHost( 'h1' ))
        hosts.append(self.addHost( 'h2' ))
        hosts.append(self.addHost( 'h3' ))
        hosts.append(self.addHost( 'h4' ))

        switches.append(self.addSwitch( 's1' ))
        switches.append(self.addSwitch( 's2' ))

        # Add links
        self.addLink(hosts[0], switches[0], cls=TCLink, delay='10ms')
        self.addLink(hosts[1], switches[0], cls=TCLink, delay='10ms')

        self.addLink(switches[0], switches[1], cls=TCLink, delay='10ms')

        self.addLink(hosts[2], switches[1], cls=TCLink, delay='10ms')
        self.addLink(hosts[3], switches[1], cls=TCLink, delay='10ms')

topos = { 'mytopo': ( lambda: MyTopo() ) }