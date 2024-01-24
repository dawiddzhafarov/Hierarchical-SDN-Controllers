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

from requests import Response
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib.hub import sleep
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib import hub, stplib
from ryu.lib import dpid as dpid_lib
from ryu.topology import api
from ryu.topology import event
from ryu.app.ofctl_rest import RestStatsApi
from aux_classes import LBEventRoleChange
from super_controller import ROLE, CMD

LOG = logging.getLogger("load_balance_lib")

ALPHA = 0.5
BETA = 1 - ALPHA

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
    _CONTEXTS = {'stplib': stplib.Stp, 'rest': RestStatsApi}

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.server_addr = kwargs.get("server_addr", "127.0.0.1")
        self.server_port = kwargs.get("server_port", 10807)
        self.global_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.mac_to_port = {}
        self.OFPIN_IN_COUNTER: int = 0
        self.controller_role: list[dict[str, str]] = []
        self.stp = kwargs['stplib']
        self.rest = kwargs['rest']

        config = {dpid_lib.str_to_dpid('0000000000000001'):
                  {'bridge': {'priority': 0x8000}},
                  dpid_lib.str_to_dpid('0000000000000002'):
                  {'bridge': {'priority': 0x9000}},
                  dpid_lib.str_to_dpid('0000000000000003'):
                  {'bridge': {'priority': 0xa000}}}
        self.stp.set_config(config)

        # TODO: uncomment when checked that one controller is elected master upon first OPFIn arrival
        # change to slave first
        # switches = api.get_all_switch(self)
        # for switch in switches:
        #     dp = switch.dp
        #     ofp = dp.ofproto
        #     ofp_parser = dp.ofproto_parser
        #     role = ofp.OFPCR_ROLE_SLAVE
        #     # generate new generation id
        #     gen_id = random.randint(0, 10000)
        #     msg = ofp_parser.OFPRoleRequest(dp, role, gen_id)
        #     dp.send_msg(msg)
        #     LOG.debug(f'sent init role request: {role} for switch: {dp}')
        #     self.controller_role.append({"dpid": dp, "role": role})

        self.start_serve()

    def delete_flow(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        for dst in self.mac_to_port[datapath.id].keys():
            match = parser.OFPMatch(eth_dst=dst)
            mod = parser.OFPFlowMod(
                datapath, command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                priority=1, match=match)
            datapath.send_msg(mod)

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
        # master: MASTER
        # slave: SLAVE
        # equal: EQUAL
        # nochange: NOCHANGE

        switch = api.get_switch(self, dpid)

        if switch is not None:
            dp = switch.dp
            ofp = dp.ofproto
            ofp_parser = dp.ofproto_parser

            if ROLE(role) == ROLE.MASTER:
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
            self.load_score = ALPHA * cpu_util + BETA * mem_util
            load_data = json.dumps({
                'cmd': f"{CMD.LOAD_UPDATE}",
                'load': self.load_score
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
            sleep(seconds=1)

    @set_ev_cls(stplib.EventTopologyChange, MAIN_DISPATCHER)
    def _topology_change_handler(self, ev):
        dp = ev.dp
        dpid_str = dpid_lib.dpid_to_str(dp.id)
        msg = 'Receive topology change event. Flush MAC table.'
        self.logger.debug("[dpid=%s] %s", dpid_str, msg)

        dp_data = json.dumps({
            'cmd': f"{CMD.DPID_REQUEST}",
            'dpid': dp
        })
        self.global_socket.sendall(dp_data)

        # request role for all connected switches
        # ad1: if a switch goes down its state is not updated, thus super_controller is updated with
        #      inaccurate info
        self._request_self_role_for_switches()

        if dp.id in self.mac_to_port:
            self.delete_flow(dp)
            del self.mac_to_port[dp.id]

        dpid2role_data = json.dumps({
            'cmd': f"{CMD.DPID_TO_ROLE}",
            'switches': self.controller_role
        })
        self.global_socket.sendall(dpid2role_data)

    @set_ev_cls(stplib.EventPortStateChange, MAIN_DISPATCHER)
    def _port_state_change_handler(self, ev):
        dpid_str = dpid_lib.dpid_to_str(ev.dp.id)
        of_state = {stplib.PORT_STATE_DISABLE: 'DISABLE',
                    stplib.PORT_STATE_BLOCK: 'BLOCK',
                    stplib.PORT_STATE_LISTEN: 'LISTEN',
                    stplib.PORT_STATE_LEARN: 'LEARN',
                    stplib.PORT_STATE_FORWARD: 'FORWARD'}
        self.logger.debug("[dpid=%s][port=%d] state=%s",
                          dpid_str, ev.port_no, of_state[ev.port_state])

    def _request_self_role_for_switches(self) -> None:
        """
        Request all connected switches for self-role
        """
        switches = api.get_all_switch(self)
        for switch in switches:
            dp = switch.dp
            self._request_controller_role(dp)
            LOG.debug(f'sent role query for switch: {dp}')

    @staticmethod
    def _request_controller_role(datapath):
        """
        Request controller role for a given DPID
        """
        ofp_parser = datapath.ofproto_parser
        req = ofp_parser.OFPCtrlMsg(
            datapath, datapath.ofproto.OFPT_ROLE_REQUEST,
            datapath.ofproto.OFPCR_ROLE_REQUEST_MORE)
        datapath.send_msg(req)
        LOG.debug(f'sent role query for switch: {datapath} with body: {req}')

    @set_ev_cls(ofp_event.EventOFPRoleReply, MAIN_DISPATCHER)
    def _role_reply_handler(self, ev):
        msg = ev.msg
        dp = msg.dp
        role = msg.role

        _new_roles = [role_dict for role_dict in self.controller_role if role_dict['dpid'] != dp]
        _new_roles.append({'dpid':dp, 'role':role})
        self.controller_role = _new_roles

        self.logger.info("Controller Role Reply received:")
        self.logger.info("Datapath ID: %s", dp)
        self.logger.info("Controller Role: %s", role)
