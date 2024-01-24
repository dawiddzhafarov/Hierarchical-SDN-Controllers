import json
import logging
import random
from sys import stdout

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.lib.hub import sleep
from ryu.topology import api
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import dpid as dpid_lib, hub
from ryu.lib import stplib
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.app import simple_switch_13
import socket
from ryu.topology import event
from src.aux_classes import LBEventRoleChange, get_ram_utilization, get_cpu_utilization
from src.super_controller import ROLE, CMD

ALPHA = 0.5
BETA = 1 - ALPHA

class LoadController(simple_switch_13.SimpleSwitch13):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'stplib': stplib.Stp}

    def __init__(self, *args, **kwargs):
        super(LoadController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.server_addr = kwargs.get("server_addr", "127.0.0.1")
        self.server_port = kwargs.get("server_port", 10807)
        self.global_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.mac_to_port = {}
        self.OFPIN_IN_COUNTER: int = 0
        self.controller_role: list[dict[str, str]] = []
        self.stp = kwargs['stplib']
        self.name = kwargs.get('name', 'default')
        self.logger = logging.getLogger(f"load_controller_{self.name}")
        logging.basicConfig(stream=stdout, level=logging.DEBUG)

        # Sample of stplib config.
        #  please refer to stplib.Stp.set_config() for details.
        config = {dpid_lib.str_to_dpid('0000000000000001'):
                  {'bridge': {'priority': 0x8000}},
                  dpid_lib.str_to_dpid('0000000000000002'):
                  {'bridge': {'priority': 0x9000}},
                  dpid_lib.str_to_dpid('0000000000000003'):
                  {'bridge': {'priority': 0xa000}}}
        self.stp.set_config(config)

        # TODO: uncomment when checked that one controller is elected master upon first OPFIn arrival
        switches = api.get_all_switch(self)
        for switch in switches:
            dp = switch.dp
            ofp = dp.ofproto
            ofp_parser = dp.ofproto_parser
            role = ofp.OFPCR_ROLE_SLAVE
            # generate new generation id
            gen_id = random.randint(0, 10000)
            msg = ofp_parser.OFPRoleRequest(dp, role, gen_id)
            dp.send_msg(msg)
            self.logger.debug(f'sent init role request: {role} for switch: {dp}')
            self.controller_role.append({"dpid": dp, "role": role})

        # self.start_serve()
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

    @set_ev_cls(stplib.EventPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
        self.OFPIN_IN_COUNTER += 1

    @set_ev_cls(event.EventSwitchEnter, MAIN_DISPATCHER)
    def _event_switch_enter_handler(self, ev):
        dpid = ev.dp.id
        self.logger.debug(f'EventSwitchEnter: {dpid=}')
        self.add_dpid(dpid)

    @set_ev_cls(LBEventRoleChange, MAIN_DISPATCHER)
    def _role_change_handler(self, ev):
        """
        Change role for a given switch based on DPID provided in LBEventRoleChange event
        """
        self.logger.debug(f'Global role change request: {ev}')
        dpid = ev.dpid
        role = ev.role

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
            self.logger.debug(f'sent role change request: {role} for switch: {dp=}')
            dp.send_msg(msg)

    def _request_controller_role(self, datapath):
        """
        Request controller role for a given DPID
        """
        ofp_parser = datapath.ofproto_parser
        gen_id = random.randint(0, 10000)
        req = ofp_parser.OFPRoleRequest(
            datapath, datapath.ofproto.OFPT_ROLE_REQUEST,
            gen_id
        )
        self.logger.debug(f'sent role query for switch: {datapath} with body: {req}')
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPRoleReply, MAIN_DISPATCHER)
    def _role_reply_handler(self, ev):
        msg = ev.msg
        dp = msg.dp
        role = msg.role

        _new_roles = [role_dict for role_dict in self.controller_role if role_dict['dpid'] != dp]
        _new_roles.append({'dpid': dp, 'role': role})
        self.controller_role = _new_roles

        self.logger.info("Controller Role Reply received:")
        self.logger.info("Datapath ID: %s", dp)
        self.logger.info("Controller Role: %s", role)

    @set_ev_cls(stplib.EventTopologyChange, MAIN_DISPATCHER)
    def _topology_change_handler(self, ev):
        dp = ev.dp
        dpid_str = dpid_lib.dpid_to_str(dp.id)
        msg = 'Receive topology change event. Flush MAC table.'
        self.logger.debug("[dpid=%s] %s", dpid_str, msg)

        if dp.id in self.mac_to_port:
            self.delete_flow(dp)
            del self.mac_to_port[dp.id]

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
        self.global_socket.sendall(dp_data.encode('utf-8'))

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
            self.global_socket.sendall(load_data.encode('utf-8'))
            _buffer = self.global_socket.recv(128)
            msg_lines = _buffer.decode('utf-8').splitlines()
            for _line in msg_lines:
                msg = json.loads(_line)
                if msg['cmd'] == CMD.ROLE_CHANGE:
                    role = msg['role']
                    dpid = msg['dpid']
                    if role == 0:
                        self.logger.debug("no need to change role.")
                        continue
                    else:
                        role_event = LBEventRoleChange(dpid, role)
                        self.logger.debug(f"role event change -> {role}")
                        # below sends event to _role_change_handler observer
                        self.send_event_to_observers(role_event)
            sleep(seconds=1)
