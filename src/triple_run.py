#!/usr/bin/python3
# vim: ft=python : ts=4 : sts=4 : sw=4 : et :
"""
Runner script for triple controllers.
"""

import sys
import os
from itertools import permutations

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.cli import CLI
from mininet.log import setLogLevel, info

from topos.abilene_topo import AbileneTopo
from topos.abilene_mod_topo import AbileneModTopo


def simple_run(topo: Topo):
    "Basic runner script."

    info('*** Creating topology\n')
    # controller=lambda name: RemoteController(name,
    #                                          ip='127.0.0.1',
    #                                          port=6653),
    net = Mininet(switch=OVSSwitch)

    c1 = net.addController('c1', controller=RemoteController, ip="127.0.0.1", port=6633)
    c2 = net.addController('c2', controller=RemoteController, ip="127.0.0.1", port=6634)
    c3 = net.addController('c3', controller=RemoteController, ip="127.0.0.1", port=6635)
    controllers = [c1, c2, c3]
    controller_perms = list(permutations(controllers))

    net.buildFromTopo(topo)
    for c in controllers:
        c.start()

    for idx, sw in enumerate(net.switches):
        sw.start(list(controller_perms[idx % 6]))

    info('*** Starting network\n')
    net.start()
    net.staticArp()

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
