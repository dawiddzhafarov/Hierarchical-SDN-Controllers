#!/usr/bin/python3
# vim: ft=python : ts=4 : sts=4 : sw=4 : et :
"""
Runner script.
"""


import sys
import os

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
     net = Mininet(topo=topo(),
                   controller=lambda name: RemoteController(name,
                                                            ip='127.0.0.1',
                                                            port=6653),
                   switch=OVSSwitch,
                   )

     info('*** Starting network\n')
     net.start()

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
