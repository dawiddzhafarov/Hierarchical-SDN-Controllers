import json
import logging
import random
from queue import Empty
from sys import stdout

from eventlet import Queue
from ryu.controller import ofp_event
from ryu.lib.hub import sleep
from ryu.topology import api
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import dpid as dpid_lib, hub
from ryu.lib import stplib
from ryu.lib import ofctl_v1_3 as ofctl
from ryu.app import simple_switch_13
import socket
from ryu.topology import event
from aux_classes import LBEventRoleChange, get_ram_utilization, get_cpu_utilization
from super_controller import ROLE, CMD
from ryu.controller import dpset
from ryu.app.ofctl_rest import RestStatsApi

ALPHA = 0.5
BETA = 1 - ALPHA

class LoadController(simple_switch_13.SimpleSwitch13):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'stplib': stplib.Stp,
                 'dpset': dpset.DPSet,
                 }

    def __init__(self, *args, **kwargs):
        super(LoadController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.server_addr = kwargs.get("server_addr", "127.0.0.1")
        self.server_port = kwargs.get("server_port", 10807)
        self.global_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.OFPIN_IN_COUNTER: int = 0
        self.sendQueue: Queue | None = Queue(32)
        self.controller_role: list[dict[str, str]] = []
        self.stp = kwargs['stplib']
        self.dpset = kwargs['dpset']
        self.name = kwargs.get('name', 'default')
        self.gen_id = 2**32 - 1
        logging.basicConfig(stream=stdout, level=logging.info)

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
        for dp, _ in self.dpset.get_all():
            ofp = dp.ofproto
            ofp_parser = dp.ofproto_parser
            # NOTE: we always want to become the master on init
            role = ofp.OFPCR_ROLE_MASTER
            # generate new generation id
            gen_id = self.gen_id
            self.gen_id += 1
            msg = ofp_parser.OFPRoleRequest(dp, role, gen_id)
            dp.send_msg(msg)
            self.logger.info(f'sent init role request: {role} for switch: {dp.id}')
            self.controller_role.append({"dpid": dp.id, "role": role})
        self.start_serve()
        self._send_roles_to_master()

    @set_ev_cls(stplib.EventPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        super()._packet_in_handler(ev)
        self.OFPIN_IN_COUNTER += 1

    @set_ev_cls(event.EventSwitchEnter, MAIN_DISPATCHER)
    def _event_switch_enter_handler(self, ev):
        dpid = ev.switch.dp.id
        self.logger.info(f'EventSwitchEnter: {dpid=}')
        self._get_self_role(ev.switch.dp, waiters={dpid: {}})
        self._request_controller_role(ev.switch.dp)
        self._send_roles_to_master()
        self._get_self_role(ev.switch.dp, waiters={dpid: {}})
        #self.add_dpid(dpid)

    @set_ev_cls(LBEventRoleChange, MAIN_DISPATCHER)
    def _role_change_handler(self, ev):
        """
        Change role for a given switch based on DPID provided in LBEventRoleChange event
        """
        self.logger.info(f'Global role change request: {ev}')
        dpid = ev.dpid
        role = ev.role

        switch = api.get_switch(self, dpid)

        if switch is not None:
            dp = switch.dp
            ofp = dp.ofproto
            ofp_parser = dp.ofproto_parser

            if ROLE(role) == ROLE.MASTER:
                role = ofp.OFPCR_ROLE_MASTER
            # else:
            #     role = ofp.OFPCR_ROLE_SLAVE
            # generate new generation id
            gen_id = self.gen_id
            self.gen_id += 1
            msg = ofp_parser.OFPRoleRequest(dp, role, gen_id)
            self.logger.info(f'sent role change request: {role} for switch: {dp=}')
            dp.send_msg(msg)

    def _request_controller_role(self, datapath):
        """
        Request controller role for a given DPID
        """
        ofp_parser = datapath.ofproto_parser

        gen_id = self.gen_id
        self.gen_id += 1
        req = ofp_parser.OFPRoleRequest(
            datapath, datapath.ofproto.OFPCR_ROLE_MASTER,
            gen_id
        )
        self.logger.info(f'sent role query for switch: {datapath} with body: {req}')
        datapath.send_msg(req)

    def _get_self_role(self, datapath, waiters):
        out = ofctl.get_role(datapath, waiters=waiters)
        self.logger.info(f'magia: {out}')

    @set_ev_cls(ofp_event.EventOFPRoleReply, MAIN_DISPATCHER)
    def _role_reply_handler(self, ev):
        self.logger.info(f'role reply: {ev=}')
        msg = ev.msg
        dp = msg.datapath
        match msg.role:
            case 0:
                role = ROLE.NOCHANGE
            case 1:
                role = ROLE.EQUAL
            case 2:
                role = ROLE.MASTER
            case 3:
                role = ROLE.SLAVE
            case _:
                self.logger.error('role unknown')

        _new_roles = [role_dict for role_dict in self.controller_role if role_dict['dpid'] != dp]
        _new_roles.append({'dpid': f'{dp.id}', 'role': role})
        self.controller_role = _new_roles
        self.logger.info("Controller Role Reply received:")
        self.logger.info("Datapath ID: %s", dp)
        self.logger.info("Controller Role: %s", role)
        dpid2role_data = json.dumps({
            'cmd': f"{CMD.DPID_TO_ROLE}",
            'switches': self.controller_role
        })
        self.send_msg_to_controller(dpid2role_data)

    def start_serve(self):
        try:
            self.global_socket.connect((self.server_addr, self.server_port))
            thread1 = hub.spawn(self._sendingLoop)
            thread2 = hub.spawn(self._balance_loop)
            thread3 = hub.spawn(self._sendLoad)
            self.threads.append(thread1)
            self.threads.append(thread2)
            self.threads.append(thread3)

        except Exception as e:
            self.logger.info(f'exception in loop: {e=}')
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
        self.send_msg_to_controller(dp_data)

    def _send_roles_to_master(self):
        dpid2role_data = json.dumps({
            'cmd': f"{CMD.DPID_TO_ROLE}",
            'switches': self.controller_role
        })
        self.send_msg_to_controller(dpid2role_data)

    def _sendingLoop(self) -> None:
        """Sending loop for a client."""
        try:
            while True:
                if self.sendQueue is not None:
                    buf = self.sendQueue.get()
                    self.global_socket.sendall(buf.encode())
                    sleep(1)
        finally:
            q = self.sendQueue
            self.sendQueue = None

            try:
                if q is not None:
                    while q.get(block=False):
                        pass
            except Empty:
                pass

    def _sendLoad(self):
        while True:
            cpu_util = get_cpu_utilization()
            mem_util = get_ram_utilization()
            self.load_score = ALPHA * cpu_util + BETA * mem_util
            load_data = json.dumps({
                'cmd': f"{CMD.LOAD_UPDATE}",
                'load': self.load_score
            })
            self.send_msg_to_controller(load_data)
            sleep(3)

    def _balance_loop(self):
        """
        keep sending cpu usage and memory usage
        and receive global controller decision
        """
        while True:
            _buffer = self.global_socket.recv(1024)
            msg_lines = _buffer.decode('utf-8').splitlines()
            for _line in msg_lines:
                msg = json.loads(_line)
                if CMD(msg['cmd']) == CMD.ROLE_CHANGE:
                    role = msg['role']
                    dpid = msg['dpid']
                    if role == ROLE.NOCHANGE.value:
                        self.logger.info("no need to change role.")
                        continue
                    else:
                        role_event = LBEventRoleChange(dpid, role)
                        self.logger.info(f"role event change -> {role}")
                        # below sends event to _role_change_handler observer
                        self.send_event_to_observers(role_event)
            sleep(seconds=1)

    def send_msg_to_controller(self, msg):
        self.sendQueue.put(msg)
