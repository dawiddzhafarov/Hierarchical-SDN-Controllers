#!/usr/bin/python3
# vim: ft=python : ts=4 : sts=4 : sw=4 : et :
"""
Runner script for triple controllers.
"""

import sys
import os
from itertools import permutations, groupby

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.topo import Topo
from mininet.cli import CLI
from mininet.log import setLogLevel, info

from topos.abilene_topo import AbileneTopo
from topos.abilene_mod_topo import AbileneModTopo


def start_net(net: Mininet):
    "Start controller and switches."
    if not net.built:
        net.build()
    info( '*** Starting controller\n' )
    for controller in net.controllers:
        info( controller.name + ' ')
        controller.start()
    info( '\n' )
    controller_perms = list(permutations(net.controllers))
    permlen = len(controller_perms)
    info( '*** Starting %s switches\n' % len( net.switches ) )
    for idx, switch in enumerate(net.switches):
        info( switch.name + ' ')
        switch.start( controller_perms[idx % permlen] )
    started = {}
    for swclass, switches in groupby(
            sorted( net.switches,
                    key=lambda s: str( type( s ) ) ), type ):
        switches = tuple( switches )
        if hasattr( swclass, 'batchStartup' ):
            success = swclass.batchStartup( switches )
            started.update( { s: s for s in success } )
    info( '\n' )
    if net.waitConn:
        net.waitConnected()


def simple_run(topo: Topo):
    "Basic runner script."

    info('*** Creating topology\n')
                  # controller=lambda name: RemoteController(name,
                  #                                          ip='127.0.0.1',
                  #                                          port=6653),
    net = Mininet(topo=topo())

    c1 = net.addController('c1', controller=RemoteController, ip="127.0.0.1", port=6653)
    c2 = net.addController('c2', controller=RemoteController, ip="127.0.0.1", port=6654)
    c3 = net.addController('c3', controller=RemoteController, ip="127.0.0.1", port=6655)

    # net.build()
    info('*** Starting network\n')
    # for c in controllers:
    #     c.start()
    #
    # for idx, sw in enumerate(net.switches):
    #     print(type(sw))
    #     sw.start(list(controller_perms[idx % 6]))

    start_net(net)
    net.staticArp()
    for name, node in net.nameToNode.items():
        print(f"{name} :{type(node)}: {node.connected()}")

    info('*** Running CLI\n')
    CLI(net)

    info('*** Stopping network')
    net.stop()


if __name__ == "__main__":
    setLogLevel('info')

    if len(sys.argv) == 1 or sys.argv[1] == 'base':
        simple_run(AbileneModTopo)
    elif sys.argv[1] == 'abilene':
        simple_run(AbileneTopo)
    else:
        print("ERROR: No such topology option.")
        sys.exit(1)
