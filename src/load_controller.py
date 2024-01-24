import json
import logging
import random
from sys import stdout

from ryu.controller import ofp_event
from ryu.lib.hub import sleep
from ryu.topology import api
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import dpid as dpid_lib, hub
from ryu.lib import stplib
from ryu.app import simple_switch_13
import socket
from ryu.topology import event
from aux_classes import LBEventRoleChange, get_ram_utilization, get_cpu_utilization
from super_controller import ROLE, CMD

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
        self.OFPIN_IN_COUNTER: int = 0
        self.controller_role: list[dict[str, str]] = []
        self.stp = kwargs['stplib']
        self.name = kwargs.get('name', 'default')
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
        #     self.logger.debug(f'sent init role request: {role} for switch: {dp}')
        #     self.controller_role.append({"dpid": dp, "role": role})
        # self.start_serve()

    @set_ev_cls(stplib.EventPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        super()._packet_in_handler(ev)
        self.OFPIN_IN_COUNTER += 1

    @set_ev_cls(event.EventSwitchEnter, MAIN_DISPATCHER)
    def _event_switch_enter_handler(self, ev):
        dpid = ev.switch.dp.id
        self.logger.debug(f'EventSwitchEnter: {dpid=}')
        #self.add_dpid(dpid)

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
            'dpid': f'{dpid}'
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
                        self.logger.debug("no need to change role.")
                        continue
                    else:
                        role_event = LBEventRoleChange(dpid, role)
                        self.logger.debug(f"role event change -> {role}")
                        # below sends event to _role_change_handler observer
                        self.send_event_to_observers(role_event)
            sleep(seconds=1)
