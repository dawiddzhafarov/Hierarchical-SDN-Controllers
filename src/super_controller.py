# -*- coding: utf-8 -*-
# vim: ts=4 : sts=4 : sw=4 : et :

import json
from sys import exit, stdout
from typing import Callable
from enum import Enum, StrEnum, auto
from logging import basicConfig, getLogger, DEBUG
from contextlib import closing
from socket import AF_INET6#, AF_UNIX
# from pathlib import Path
from ipaddress import IPv6Address, AddressValueError
from traceback import format_exc
from socket import socket

import networkx as nx
from eventlet import Timeout, listen, spawn
from eventlet.queue import Empty, Queue
from eventlet.greenthread import GreenThread, sleep
from greenlet import GreenletExit

logger = getLogger("SDN_SuperController")
basicConfig(stream=stdout, level=DEBUG)

WORKER_LIMIT = 1024
LOAD_THRESHOLD = 0.7
TIME_BALANCING = 1
TIMEOUT = 300

class ROLE(StrEnum):
    """Roles for OpenFlow v1.3.

    Enum:
        master   -> MASTER
        slave    -> SLAVE
        equal    -> EQUAL
        nochange -> NOCHANGE
    """
    MASTER = auto()
    SLAVE = auto()
    EQUAL = auto()
    NOCHANGE = auto()

    def __repr__(self):
        return f"{self.name.upper()}"


class CMD(StrEnum):
    """Commands to exchange between super controller and domain controllers.

    Enum:
        keepalive     -> KEEPALIVE
        workerid_set  -> WORKERID_SET
        xdom_link_add -> XDOM_LINK_ADD
        host_response -> HOST_RESPONSE
        route_request -> ROUTE_REQUEST
        route_result  -> ROUTE_RESULT
        dpid_request  -> DPID_REQUEST
        dpid_response -> DPID_RESPONSE
        load_update   -> LOAD_UPDATE
        role_change   -> ROLE_CHANGE
        dpid_to_role  -> DPID_TO_ROLE
    """
    KEEPALIVE = auto()
    WORKERID_SET = auto()
    XDOM_LINK_ADD = auto()
    HOST_RESPONSE = auto()
    ROUTE_REQUEST = auto()
    ROUTE_RESULT = auto()
    DPID_REQUEST = auto()
    DPID_RESPONSE = auto()
    LOAD_UPDATE = auto()
    ROLE_CHANGE = auto()
    DPID_TO_ROLE = auto()

    def __repr__(self):
        return f"{self.name.lower()}"


class SCWSEventBase(object):
    """Base for SC Server and Worker. This is wrapper for eventlet workflow."""

    @staticmethod
    def spawnThread(*args, **kwargs) -> GreenThread:
        """Taken from `ryu.lib.hub` to limit dependencies."""
        raise_error = kwargs.pop('raise_error', False)

        def _launch(func: Callable, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except GreenletExit:
                pass
            except BaseException as e:
                if raise_error:
                    raise e
                logger.error(f"Uncaught exception: {format_exc()}")

        return spawn(_launch, *args, **kwargs)


    @staticmethod
    def joinAll(threads: list[GreenThread]) -> None:
        """Taken from `ryu.lib.hub` to limit dependencies.

        Args:
            threads: list of threads to await for actions
        """
        for t in threads:
            try:
                t.wait()
            except GreenletExit:
                pass


class SCServer:
    """Simple server for accepting connections and spawning workers.

    Attributes:
        server: eventlet listening server instance
        handle: handler function to spawn workers
    """

    def __init__(self, listen_info: tuple[str, int], handle: Callable | None = None):
        try:
            IPv6Address(listen_info[0])
            self.server = listen(listen_info, family=AF_INET6)
        except AddressValueError:
            self.server = listen(listen_info)

        self.handle = handle


    def serveForever(self) -> None:
        """Infinite loop to spawn connections."""
        while True:
            sock, addr = self.server.accept()
            SCWSEventBase.spawnThread(self.handle, sock, addr)


class SCWorker:
    """This is a websocket worker to accept connections from domain controllers
    and send and receive messages through websocket API.

    Attributes:
        webSocket: websocket to send and receive
        clientAddress: address of a client controller
        sQueue: eventlet sending Queue
        isActive: if the worker thread is active
        workerID: id of a worker
        loadScore: score of load provided by domain controller
        _overseerController: SuperController to handle all the actions for clients
    """

    def __init__(self, socket: socket, address: tuple[str, int]):
        super(SCWorker, self).__init__()
        self.webSocket = socket
        self.clientAddress: tuple[str, int] = address
        self.sendQueue: Queue | None = Queue(32)
        self.isActive: bool = True
        self.workerID: int = -1
        self.loadScore: float = 0
        self.dpid2role: dict[str, ROLE] = {}
        self._overseerController: SuperController | None = None


    def setWorkerID(self, worker_id: int) -> None:
        """Set workerID and propagate it to a client.

        Args:
            worker_id: new ID for a worker
        """
        self.workerID = worker_id
        msg = json.dumps({
            'cmd': f"{CMD.WORKERID_SET}",
            'worker_id': worker_id,
        })

        self.sendMsg(msg)


    def sendMsg(self, msg: str) -> None:
        """Send message to a worker.

        Args:
            msg: stringified json to be sent to a client
        """
        logger.info(f"{msg = }")
        if self.sendQueue:
            self.sendQueue.put(msg)


    def _processMsg(self, msg: dict) -> None:
        """Process message from client.

        Args:
            msg: dictified json message to process
        """
        logger.debug(f"Received: {msg= }")
        if self._overseerController is not None:
            match CMD(msg["cmd"]):
                case CMD.KEEPALIVE:
                    return

                case CMD.XDOM_LINK_ADD:
                    src, dst = msg['src'], msg['dst']
                    logger.debug(f"Got cross-domain link message from {self.workerID}: {src= }, {dst= }")
                    self._overseerController.handleXDomLinkAdd(src, dst, self.workerID)

                case CMD.HOST_RESPONSE:
                    host = msg['host']
                    logger.debug(f"Got host to worker assignment from {self.workerID} for {host= }")
                    self._overseerController.handleHostResponse(host, self.workerID)

                case CMD.ROUTE_REQUEST:
                    dst_host = msg['dst']
                    logger.debug(f"Got request from {self.workerID} for route to {dst_host= }")
                    self._overseerController.handleRouteRequest(dst_host, self.workerID)

                case CMD.DPID_RESPONSE:
                    dpid = msg['dpid']
                    logger.debug(f"Got switch to worker assignment msg from {self.workerID} for {dpid= }")
                    self._overseerController.handleDpidResponse(dpid, self.workerID)

                case CMD.LOAD_UPDATE:
                    load = msg['load']
                    logger.debug(f"Got load update from worker{self.workerID}: {load= }")
                    self._overseerController.handleLoadUpdate(float(load), self.workerID)

                case CMD.DPID_TO_ROLE:
                    switches = msg['switches']
                    logger.debug(f"Got role status from worker{self.workerID} for {switches= }")
                    self._overseerController.handleDpidToRole(switches, self.workerID)

                case _:
                    logger.error(f"No such {msg= }")


    def _sendingLoop(self) -> None:
        """Sending loop for a client."""
        try:
            while self.isActive:
                if self.sendQueue is not None:
                    buf = self.sendQueue.get()
                    self.webSocket.sendall(buf.encode())
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


    def _receivingLoop(self) -> None:
        """Receiving loop for a client."""
        with Timeout(TIMEOUT, False):
            while self.isActive:
                try:
                    _buffer = self.webSocket.recv(1024)

                    if len(_buffer) == 0:
                        sleep(1)
                        continue

                    msg_lines = _buffer.decode('utf-8').splitlines()
                    for _line in msg_lines:
                        msg = json.loads(_line)
                        self._processMsg(msg)

                    sleep(1)
                except ValueError:
                    logger.warning(f"Value error for {_line= }, len: {len(_line)}")

        logger.info(f"Connection with {self.clientAddress} timed out.")
        self.isActive = False


    def serve(self) -> None:
        """Spawn sending and receiving threads for a client."""
        thread1 = SCWSEventBase.spawnThread(self._sendingLoop)
        thread2 = SCWSEventBase.spawnThread(self._receivingLoop)
        SCWSEventBase.joinAll([thread1, thread2])


    @property
    def numControlledSwitches(self) -> int:
        """Calculate the number of switches that have this controlled as master.

        Returns:
            number of switches it is a master for
        """
        result = 0
        for k in self.dpid2role:
            result += 1 if self.dpid2role[k] in [ROLE.MASTER, ROLE.EQUAL] else 0
        return result

    def close(self) -> None:
        """Deactivate and close the worker thread."""
        self.isActive = False
        self.webSocket.close()


class SuperController:
    """SuperController class to manage links between domains
    and manage switch handover from domain to another.

    Attributes:
        workers: map of workerIDs to workerThreads
        server: WebSocket server to accept connections from controllers
                  and spawn workers for them
        xdom_links: links between domains
        hosts: map of host mac assignment to worker_id
    """

    def __init__(self, bind_address: str = "0.0.0.0", bind_port: int = 10807):
        super(SuperController, self).__init__()
        self.workers: dict[int, SCWorker] = {}
        self.server: SCServer = SCServer((bind_address, bind_port), self._connectionFactory)
        self.xdom_links: list[dict[str, dict[str, str | int]]] = []
        self.hosts: dict[str, int] = {}


    # . BEGIN SuperController utils {
    def _connectionFactory(self, sock: socket, addr: tuple[str, int]) -> None:
        """Connection handler for SuperController Server.

        Args:
            sock: socket object to bound connection to
            addr: address tuple of a client
        """
        logger.info(f"Connected with client: {addr} on socket: {sock}")

        with closing(SCWorker(sock, addr)) as worker:
            worker._overseerController = self
            worker_id = len(self.workers)

            while worker_id in self.workers:
                worker_id = (worker_id + 1) % WORKER_LIMIT

            worker.setWorkerID(worker_id)
            self.workers[worker_id] = worker

            worker.serve()

            logger.info(f"Remove client worker -> ID:{worker_id}")
            del self.workers[worker_id]


    def start(self) -> None:
        """Start accepting clients."""
        thread1 = SCWSEventBase.spawnThread(self._sendingLoop)
        logger.info('Waiting for connection...')
        self.server.serveForever()

        SCWSEventBase.joinAll([thread1])


    def printWorkerStatus(self) -> None:
        """Show agent status. (helper func)"""
        for wid, worker in sorted(self.workers.items()):
            print(f"Worker{wid} => {worker.clientAddress} :: {worker.__str__()}")


    def _findFreeControllers(self, busy_controller_id: int) -> int | None:
        """Find free or low loaded controller.

            Free controller find dynamics:
                * lower load score
                * less switches under control (role == MASTER)

        Args:
            busy_controller_id: id of a controller/worker that you want to find less
                                loaded controller

        Returns:
            id of a worker that is less loaded then provided
        """
        free_controller = None
        controllers = sorted(
            self.workers.items(),
            key=lambda x: (x[1].loadScore, x[1].numControlledSwitches)
        )

        for wid, ctrl in controllers:

            if ctrl.loadScore < LOAD_THRESHOLD and wid is not busy_controller_id:
                free_controller = wid
                break

        return free_controller


    def _balanceControllers(self, busy_worker_id: int, free_worker_id: int) -> None:
        """Move one switch from busy to free.

        Args:
            busy_worker_id: id of a busy controller/worker
            free_worker_id: id of a free controller/worker
        """
        for dpid, role in self.workers[busy_worker_id].dpid2role.items():
            if role [ROLE.MASTER.value, ROLE.SLAVE.value] and dpid in self.workers[free_worker_id].dpid2role.keys():
                msg = json.dumps({
                    'cmd': f"{CMD.ROLE_CHANGE}",
                    'role': ROLE.SLAVE.value,
                    'dpid': dpid,
                })
                self.workers[busy_worker_id].sendMsg(msg)
                self.workers[busy_worker_id].dpid2role[dpid] = ROLE.SLAVE
                msg = json.dumps({
                    'cmd': f"{CMD.ROLE_CHANGE}",
                    'role': ROLE.MASTER.value,
                    'dpid': dpid,
                })
                self.workers[free_worker_id].sendMsg(msg)
                self.workers[free_worker_id].dpid2role[dpid] = ROLE.MASTER

    def _sendingLoop(self) -> None:
        """Sending loop for the server balancing task."""
        while True:
            for wid, worker in self.workers.items():
                free_controller = None

                if worker.loadScore > LOAD_THRESHOLD:
                    free_controller = self._findFreeControllers(wid)

                if free_controller is not None:
                    self._balanceControllers(wid, free_controller)

            sleep(TIME_BALANCING)


    def broadcastThroughWorkers(self, msg: str) -> None:
        """Indirect call to propagate message to all clients.

        Args:
            msg: stringified json message to be sent
        """
        logger.debug(f"Broadcasting to all controllers: {msg= }")
        for _, worker in self.workers.items():
            worker.sendMsg(msg)


    def _getWorkerLink(self, src: str, dst: str) -> dict[str, dict[str, str | int]] | None:
        """Get link between workers.

        Args:
            src: source part from the edge tuple in networkx path
            dst: destination part from the edge tuple in networkx path

        Returns:
            link from xdom_links
        """
        # convert a? to ?
        src_worker_id = int(src[1:])
        dst_worker_id = int(dst[1:])

        for glink in self.xdom_links:
            srcg = glink['src']
            dstg = glink['dst']
            if srcg['worker_id'] == src_worker_id and dstg['worker_id'] == dst_worker_id:
                return glink

        return None


    def _getWorkerLinks(self) -> list[tuple[str, str]]:
        """Create a list of links to be injected into networkx graph.

        Returns:
            list of links in the form of ('a1', 'a2')
        """
        links = list()

        for glink in self.xdom_links:
            src = glink['src']
            dst = glink['dst']

            if 'worker_id' in src and 'worker_id' in dst:
                src = f"a{src['worker_id']}"
                dst = f"a{dst['worker_id']}"
                links.append((src, dst))

        return links
    # . END SuperController utils }


    # BEGIN SuperController handlers {
    def handleXDomLinkAdd(self, src: dict, dst: dict, worker_id: int) -> None:
        """Add link between domains.

        Args:
            src: source info
            dst: destination info
            worker_id: id of a worker which spawned the action
        """
        src['worker_id'] = worker_id
        link = {'src': src, 'dst': dst}
        link_rev = {'src': dst, 'dst': src}

        msg = json.dumps({
            'cmd': f"{CMD.DPID_REQUEST}",
            'dpid': dst['dpid'],
        })
        self.broadcastThroughWorkers(msg)

        for _link in self.xdom_links:

            if _link['src']['dpid'] == src['dpid'] and _link['src']['port'] == src['port']:
                _link['src']['agent_id'] = worker_id
                break

            if _link['dst']['dpid'] == src['dpid'] and _link['dst']['port'] == src['port']:
                _link['dst']['agent_id'] = worker_id
                break

        else:
            self.xdom_links.append(link)
            self.xdom_links.append(link_rev)


    def handleRouteRequest(self, dst_host: str, worker_id: int) -> None:
        """Get route to host and reply to asking client.

        Args:
            dst_host: mac address of the host to get route to
            worker: source worker for domain controller
        """
        if dst_host not in self.hosts:
            msg = json.dumps({
                'cmd': f"{CMD.ROUTE_RESULT}",
                'dpid': -1,
                'port': -1,
                'host': dst_host
            })
            logger.debug(f"Unknown host: {dst_host}")
            self.workers[worker_id].sendMsg(msg)
            return

        src = f"a{worker_id}"
        dst = f"a{self.hosts[dst_host]}"

        links = self._getWorkerLinks()
        g = nx.Graph(links)
        path = []
        if nx.has_path(g, src, dst):
            path = nx.shortest_path(g, src, dst)

        # NOTE: here lsp will yell at you, cause typehints in networkx are screwed
        glink = self._getWorkerLink(path[0], path[1]) or {}
        output_dpid = glink.get('src', {}).get('dpid', -1)
        output_port = glink.get('src', {}).get('port', -1)

        msg = json.dumps({
            'cmd': f"{CMD.ROUTE_RESULT}",
            'dpid': output_dpid,
            'port': output_port,
            'host': dst_host
        })
        logger.debug(f"Send route result to worker {worker_id}, {output_dpid}::{output_port} {dst_host}")
        self.workers[worker_id].sendMsg(msg)


    def handleHostResponse(self, host: str, worker_id: int) -> None:
        """Assign host to a worker/domain controller it belongs to.

        Args:
            host: host mac address string
            worker_id: id of a worker to assign host to
        """
        self.hosts[host] = worker_id
        logger.debug(f"Add host {host} to worker{worker_id} in hosts")


    def handleDpidResponse(self, dpid: str | int, worker_id: int) -> None:
        """Assign worker/domain controller to switch.

        Args:
            dpid: DatapathID of a switch
            worker_id: id of a worker to assign switch to
        """
        for _link in self.xdom_links:
            if _link['src']['dpid'] == dpid:
                _link['src']['worker_id'] = worker_id

            if _link['dst']['dpid'] == dpid:
                _link['dst']['worker_id'] = worker_id


    def handleLoadUpdate(self, load: float, worker_id: int) -> None:
        """Assign calculated load to worker/controller.

        Args:
            load: calculated by the controller self load
            worker_id: id of a worker that it should be assigned to
        """
        self.workers[worker_id].loadScore = load


    def handleDpidToRole(self, switches: list[dict[str, str]], worker_id: int) -> None:
        """Assign calculated load to worker/controller.

        Args:
            switches: list of switches and roles of the controller this data was sent from
            worker_id: id of a worker that it should be assigned to
        """
        self.workers[worker_id].dpid2role = {sw['dpid']: ROLE(sw['role'].lower()) for sw in switches}
    # . END SuperController handlers }


def sc_run() -> int:
    try:
        SuperController().start()
        return 0
    except KeyboardInterrupt:
        logger.warning("Killing server...")
        return 1


if __name__ == '__main__':
    exit(sc_run())

