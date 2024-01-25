#!/usr/bin/python3
# vim: ts=4 : sts=4 : sw=4 : et :
"""
Base topology for testing hierarchical SDN controller setup
"""

from mininet.topo import Topo
from mininet.node import OVSSwitch


class AbileneModTopo(Topo):
    "Class for topo based on Modified Abilene topology."

    def __init__(self, **opts):
        "Create topology and connect devices."
        Topo.__init__(self, **opts)

        # add hosts
        h1  = self.addHost('h_sea')
        h2  = self.addHost('h_sjc')
        h3  = self.addHost('h_den')
        h4  = self.addHost('h_lax')
        h5  = self.addHost('h_mci')
        h6  = self.addHost('h_hou')
        h7  = self.addHost('h_ord')
        h8  = self.addHost('h_atl')
        h9  = self.addHost('h_iad')
        h10 = self.addHost('h_nyc')

        # add switches
        s1  = self.addSwitch('sw_sea', dpid="00:00:00:00:00:00:00:01", cls=OVSSwitch, protocols="OpenFlow13")
        s2  = self.addSwitch('sw_sjc', dpid="00:00:00:00:00:00:00:02", cls=OVSSwitch, protocols="OpenFlow13")
        s3  = self.addSwitch('sw_den', dpid="00:00:00:00:00:00:00:03", cls=OVSSwitch, protocols="OpenFlow13")
        s4  = self.addSwitch('sw_lax', dpid="00:00:00:00:00:00:00:04", cls=OVSSwitch, protocols="OpenFlow13")
        s5  = self.addSwitch('sw_mci', dpid="00:00:00:00:00:00:00:05", cls=OVSSwitch, protocols="OpenFlow13")
        s6  = self.addSwitch('sw_hou', dpid="00:00:00:00:00:00:00:06", cls=OVSSwitch, protocols="OpenFlow13")
        s7  = self.addSwitch('sw_ord', dpid="00:00:00:00:00:00:00:07", cls=OVSSwitch, protocols="OpenFlow13")
        s8  = self.addSwitch('sw_atl', dpid="00:00:00:00:00:00:00:08", cls=OVSSwitch, protocols="OpenFlow13")
        s9  = self.addSwitch('sw_iad', dpid="00:00:00:00:00:00:00:09", cls=OVSSwitch, protocols="OpenFlow13")
        s10 = self.addSwitch('sw_nyc', dpid="00:00:00:00:00:00:00:10", cls=OVSSwitch, protocols="OpenFlow13")

        # basic setup hosts behind switches
        self.addLink(h1,  s1,  addr1="10:00:00:00:01:01", addr2="00:00:00:00:01:ff")
        self.addLink(h2,  s2,  addr1="10:00:00:00:02:01", addr2="00:00:00:00:02:ff")
        self.addLink(h3,  s3,  addr1="10:00:00:00:03:01", addr2="00:00:00:00:03:ff")
        self.addLink(h4,  s4,  addr1="10:00:00:00:04:01", addr2="00:00:00:00:04:ff")
        self.addLink(h5,  s5,  addr1="10:00:00:00:05:01", addr2="00:00:00:00:05:ff")
        self.addLink(h6,  s6,  addr1="10:00:00:00:06:01", addr2="00:00:00:00:06:ff")
        self.addLink(h7,  s7,  addr1="10:00:00:00:07:01", addr2="00:00:00:00:07:ff")
        self.addLink(h8,  s8,  addr1="10:00:00:00:08:01", addr2="00:00:00:00:08:ff")
        self.addLink(h9,  s9,  addr1="10:00:00:00:09:01", addr2="00:00:00:00:09:ff")
        self.addLink(h10, s10, addr1="10:00:00:00:10:01", addr2="00:00:00:00:10:ff")

        # proper topology
        self.addLink(s1,  s2,  addr1="00:00:00:00:01:02", addr2="00:00:00:00:02:01") # sea <-> sjc
        self.addLink(s1,  s3,  addr1="00:00:00:00:01:03", addr2="00:00:00:00:03:01") # sea <-> den
        self.addLink(s2,  s4,  addr1="00:00:00:00:02:04", addr2="00:00:00:00:04:02") # sjc <-> lax
        self.addLink(s2,  s3,  addr1="00:00:00:00:02:03", addr2="00:00:00:00:03:02") # sjc <-> den
        self.addLink(s4,  s6,  addr1="00:00:00:00:04:06", addr2="00:00:00:00:06:04") # lax <-> hou
        self.addLink(s3,  s5,  addr1="00:00:00:00:03:05", addr2="00:00:00:00:05:03") # den <-> mci
        self.addLink(s5,  s6,  addr1="00:00:00:00:05:06", addr2="00:00:00:00:06:05") # mci <-> hou
        self.addLink(s5,  s7,  addr1="00:00:00:00:05:07", addr2="00:00:00:00:07:05") # mci <-> ord
        self.addLink(s6,  s8,  addr1="00:00:00:00:06:08", addr2="00:00:00:00:08:06") # hou <-> atl
        self.addLink(s7,  s8,  addr1="00:00:00:00:07:08", addr2="00:00:00:00:08:07") # ord <-> atl
        self.addLink(s8,  s9,  addr1="00:00:00:00:08:09", addr2="00:00:00:00:09:08") # atl <-> iad
        self.addLink(s7,  s10, addr1="00:00:00:00:07:10", addr2="00:00:00:00:10:07") # ord <-> nyc
        self.addLink(s9,  s10, addr1="00:00:00:00:09:10", addr2="00:00:00:00:10:09") # iad <-> nyc

topos = {
    'abilene_mod': AbileneModTopo
}
