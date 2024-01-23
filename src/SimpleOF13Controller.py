# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import psutil
import socket
import struct
import logging
import random
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib.hub import sleep
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib import hub
from ryu.topology import api
from ryu.topology import event
from aux_classes import LBEventRoleChange
from super_controller import ROLE, CMD

LOG = logging.getLogger("load_balance_lib")
# struct consists of a single unsigned byte (8 bits).
HeaderStruct = struct.Struct("!B")
# the struct consists of an unsigned integer (32 bits).
DPStruct = struct.Struct("!I")
# struct consists of two unsigned bytes (16 bits each), effectively forming a 16-bit unsigned integer.
# third byte represents OFPacketIn counter
UtilStruct = struct.Struct("!BBB")
# struct combines an unsigned integer (32 bits) followed by an unsigned byte (8 bits) in its binary representation.
RoleStruct = struct.Struct("!IB")


def get_cpu_utilization(interval: int = 1) -> int:
    return int(psutil.cpu_percent(interval=interval))


def get_ram_utilization() -> int:
    ram = psutil.virtual_memory()
    return int(ram.percent)


class SimpleSwitch13(app_manager.RyuApp):
    """
    Implements a simple OF1.3 Switch controller which periodically listens sends its utilization
    to master controller and listens for role change request.

    Upon role request change received from master, the controller notifies its switches to reroute
    lookup requests to secondary controller
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.server_addr = kwargs.get("server_addr", "0.0.0.0")
        self.server_port = kwargs.get("server_port", 10807)
        self.global_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.mac_to_port = {}
        self.OFPIN_IN_COUNTER: int = 0

        switches = api.get_all_switch(self)

        # change to slave first
        for switch in switches:
            dp = switch.dp
            ofp = dp.ofproto
            ofp_parser = dp.ofproto_parser
            role = ofp.OFPCR_ROLE_SLAVE
            # generate new generation id
            gen_id = random.randint(0, 10000)
            msg = ofp_parser.OFPRoleRequest(dp, role, gen_id)
            dp.send_msg(msg)
            LOG.debug(f'sent init role request: {role} for switch: {dp}')

        self.start_serve()

    set_ev_cls(event.EventSwitchEnter, MAIN_DISPATCHER)
    def _event_switch_enter_handler(self, ev):
        dpid = ev.dp.id
        self.add_dpid(dpid)

    @set_ev_cls(LBEventRoleChange, MAIN_DISPATCHER)
    def _role_change_handler(self, ev):
        """
        Change role for a given switch based on DPID provided in LBEventRoleChange event
        """
        dpid = ev.dpid
        role = ev.role
        # Role:
        # 1: master
        # 2: slave

        switch = api.get_switch(self, dpid)

        if switch is not None:
            dp = switch.dp
            ofp = dp.ofproto
            ofp_parser = dp.ofproto_parser

            if role == 1:
                role = ofp.OFPCR_ROLE_MASTER

            else:
                role = ofp.OFPCR_ROLE_SLAVE
            # generate new generation id
            gen_id = random.randint(0, 10000)
            msg = ofp_parser.OFPRoleRequest(dp, role, gen_id)
            dp.send_msg(msg)
            LOG.debug(f'sent role change request: {role} for switch: {dp}')

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath, priority=priority, match=match, instructions=inst
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug(
                "packet truncated: only %s of %s bytes",
                ev.msg.msg_len,
                ev.msg.total_len,
            )
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        dst = eth.dst
        src = eth.src

        dpid = format(datapath.id, "d").zfill(16)
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

        # increment data counter by 1 each time a OFPacketIn event occurs
        self.OFPIN_IN_COUNTER += 1

    def start_serve(self):
        try:
            self.global_socket.connect((self.server_addr, self.server_port))
            hub.spawn(self._balance_loop)
        except Exception as e:
            raise e

    def add_dpid(self, dpid: int):
        """
        Send data over socket:
        1) send header (HeaderStruct) with integer value 1,
           which informs that next struct contains DPID
        2) send DPID (DPStruct) with DPID value
        """
        dp_data = json.dumps({
            'cmd': f"{CMD.DPID_REQUEST}",
            'dpid': dpid
        })
        self.global_socket.sendall(dp_data)

    def _balance_loop(self):
        """
        keep sending cpu usage and memory usage
        and receive global controller decision
        """
        while True:
            cpu_util = get_cpu_utilization()
            mem_util = get_ram_utilization()

            load_data = json.dumps({
                'cmd': f"{CMD.LOAD_UPDATE}",
                'load': cpu_util if self.OFPIN_IN_COUNTER == 0 else self.OFPIN_IN_COUNTER
            })
            self.global_socket.sendall(load_data)
            _buffer = self.global_socket.recv(128)
            msg_lines = _buffer.decode('utf-8').splitlines()
            for _line in msg_lines:
                msg = json.loads(_line)
                if msg['cmd'] == CMD.ROLE_CHANGE:
                    role = msg['role']
                    dpid = msg['dpid']
                    if role == 0:
                        LOG.debug("no need to change role.")
                        continue
                    else:
                        role_event = LBEventRoleChange(dpid, role)
                        LOG.debug(f"role event change -> {role}")
                        # below sends event to _role_change_handler observer
                        self.send_event_to_observers(role_event)
            sleep(seconds=3)
