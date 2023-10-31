#!/usr/bin/python3
# vim: ts=4 : sts=4 : sw=4 : et :
"""
Bigger topology for testing hierarchical SDN controller setup
"""

from mininet.topo import Topo


class AbileneTopo(Topo):
    "Class for topo based on Abilene topology."

    def __init__(self, **opts):
        "Create topology and connect devices."
        Topo.__init__(self, **opts)

        # add hosts
        h1  = self.addHost('h-sea')
        h2  = self.addHost('h-sjc')
        h3  = self.addHost('h-den')
        h4  = self.addHost('h-lax')
        h5  = self.addHost('h-mci')
        h6  = self.addHost('h-hou')
        h7  = self.addHost('h-ind')
        h8  = self.addHost('h-atl')
        h9  = self.addHost('h-ord')
        h10  = self.addHost('h-iad')
        h11 = self.addHost('h-nyc')

        # add switches
        s1  = self.addSwitch('sw-sea')
        s2  = self.addSwitch('sw-sjc')
        s3  = self.addSwitch('sw-den')
        s4  = self.addSwitch('sw-lax')
        s5  = self.addSwitch('sw-mci')
        s6  = self.addSwitch('sw-hou')
        s7  = self.addSwitch('sw-ind')
        s8  = self.addSwitch('sw-atl')
        s9  = self.addSwitch('sw-ord')
        s10 = self.addSwitch('sw-iad')
        s11 = self.addSwitch('sw-nyc')

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
        self.addLink(h11, s11, addr1="10:00:00:00:11:01", addr2="00:00:00:00:11:ff")

        # proper topology
        self.addLink(s1,  s2,  addr1="00:00:00:00:01:02", addr2="00:00:00:00:02:01") # sea <-> sjc
        self.addLink(s1,  s3,  addr1="00:00:00:00:01:03", addr2="00:00:00:00:03:01") # sea <-> den
        self.addLink(s2,  s4,  addr1="00:00:00:00:02:04", addr2="00:00:00:00:04:02") # sjc <-> lax
        self.addLink(s2,  s3,  addr1="00:00:00:00:02:03", addr2="00:00:00:00:03:02") # sjc <-> den
        self.addLink(s4,  s6,  addr1="00:00:00:00:04:06", addr2="00:00:00:00:06:04") # lax <-> hou
        self.addLink(s3,  s5,  addr1="00:00:00:00:03:05", addr2="00:00:00:00:05:03") # den <-> mci
        self.addLink(s5,  s6,  addr1="00:00:00:00:05:06", addr2="00:00:00:00:06:05") # mci <-> hou
        self.addLink(s5,  s7,  addr1="00:00:00:00:05:07", addr2="00:00:00:00:07:05") # mci <-> ind
        self.addLink(s6,  s8,  addr1="00:00:00:00:06:08", addr2="00:00:00:00:08:06") # hou <-> atl
        self.addLink(s7,  s8,  addr1="00:00:00:00:07:08", addr2="00:00:00:00:08:07") # ind <-> atl
        self.addLink(s7,  s9,  addr1="00:00:00:00:07:09", addr2="00:00:00:00:09:07") # ind <-> ord
        self.addLink(s8,  s10, addr1="00:00:00:00:08:10", addr2="00:00:00:00:10:08") # atl <-> iad
        self.addLink(s9,  s11, addr1="00:00:00:00:09:11", addr2="00:00:00:00:11:09") # ord <-> nyc
        self.addLink(s10, s11, addr1="00:00:00:00:10:11", addr2="00:00:00:00:11:10") # iad <-> nyc

topos = {
    'abilene': AbileneTopo
}
