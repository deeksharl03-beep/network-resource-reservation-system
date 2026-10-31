import json
import os
import socket

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet

# ---------------- Configuration ----------------
# Control channel: the reservation server (running inside Mininet host h4) sends
# policy commands to this controller over this socket. A filesystem (UNIX) socket is
# used because Mininet hosts are separate *network* namespaces but share the filesystem,
# so h4 can reach the controller (which lives in the root namespace).
SDN_SOCKET_PATH = os.environ.get("SDN_SOCKET_PATH", "/tmp/sdn_controller.sock")
TOTAL_BANDWIDTH = 1000                 # Mbps, same as the server
RESERVATION_PRIORITY = 100             # higher than the table-miss rule (priority 0)
USE_METER = False                      # True = also rate-limit with an OpenFlow meter (bonus)

# Mininet host name -> IP address
CLIENT_IPS = {"h1": "10.0.0.1", "h2": "10.0.0.2", "h3": "10.0.0.3"}
FULL_MASK = 0xFFFFFFFFFFFFFFFF


class ResourceReservationSDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ResourceReservationSDN, self).__init__(*args, **kwargs)
        self.datapaths = {}        # dpid -> datapath (connected switches)
        self.reservations = {}     # client_id -> {"cookie", "ip", "bw"}
        self.next_cookie = 1
        print("[SDN Controller] Resource Reservation OpenFlow Controller Started.")
        hub.spawn(self._policy_listener)   # start the Socket-SDN integration channel

    # ------------------------------------------------------------------
    # OpenFlow side
    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.datapaths[datapath.id] = datapath

        # Install table-miss flow entry (Default flow to controller)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        print(f"[SDN Controller] Handshake complete with Switch Datapath ID: {datapath.id}")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None,
                 cookie=0, meter_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = []
        if meter_id is not None:
            inst.append(parser.OFPInstructionMeter(meter_id))
        inst.append(parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions))

        kwargs = dict(datapath=datapath, priority=priority, match=match,
                      instructions=inst, cookie=cookie)
        if buffer_id:
            kwargs["buffer_id"] = buffer_id
        datapath.send_msg(parser.OFPFlowMod(**kwargs))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=msg.data)
        datapath.send_msg(out)

    # ------------------------------------------------------------------
    # Reservation policy (called when the TCP server accepts / expires a request)
    # ------------------------------------------------------------------
    def install_reservation(self, client_id, bandwidth):
        """Validate the request, then push a flow rule (and optional meter) to every switch."""
        if client_id not in CLIENT_IPS:
            return {"status": "ERROR", "reason": f"Unknown client {client_id}"}
        if not isinstance(bandwidth, int) or bandwidth <= 0 or bandwidth > TOTAL_BANDWIDTH:
            return {"status": "ERROR", "reason": f"Invalid bandwidth {bandwidth}"}
        if client_id in self.reservations:
            return {"status": "ERROR", "reason": f"Policy already installed for {client_id}"}
        if not self.datapaths:
            return {"status": "ERROR", "reason": "No OpenFlow switch connected"}

        cookie = self.next_cookie
        self.next_cookie += 1
        ip = CLIENT_IPS[client_id]

        for dp in self.datapaths.values():
            ofproto = dp.ofproto
            parser = dp.ofproto_parser
            meter_id = None
            if USE_METER:
                meter_id = cookie
                bands = [parser.OFPMeterBandDrop(rate=bandwidth * 1000, burst_size=0)]
                dp.send_msg(parser.OFPMeterMod(datapath=dp, command=ofproto.OFPMC_ADD,
                                               flags=ofproto.OFPMF_KBPS,
                                               meter_id=meter_id, bands=bands))
            # Traffic coming FROM the reserving client gets this high-priority rule
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src=ip)
            actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
            self.add_flow(dp, RESERVATION_PRIORITY, match, actions,
                          cookie=cookie, meter_id=meter_id)

        self.reservations[client_id] = {"cookie": cookie, "ip": ip, "bw": bandwidth}
        print(f"[SDN Controller] INSTALLED policy for {client_id} ({ip}): "
              f"{bandwidth} Mbps, cookie={cookie}, priority={RESERVATION_PRIORITY}")
        return {"status": "OK", "cookie": cookie}

    def remove_reservation(self, client_id):
        res = self.reservations.pop(client_id, None)
        if res is None:
            return {"status": "ERROR", "reason": f"No policy for {client_id}"}

        for dp in self.datapaths.values():
            ofproto = dp.ofproto
            parser = dp.ofproto_parser
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp, cookie=res["cookie"], cookie_mask=FULL_MASK,
                table_id=ofproto.OFPTT_ALL, command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                match=parser.OFPMatch()))
            if USE_METER:
                dp.send_msg(parser.OFPMeterMod(datapath=dp, command=ofproto.OFPMC_DELETE,
                                               flags=ofproto.OFPMF_KBPS,
                                               meter_id=res["cookie"], bands=[]))
        print(f"[SDN Controller] REMOVED policy for {client_id} (cookie={res['cookie']})")
        return {"status": "OK"}

    # ------------------------------------------------------------------
    # Socket-SDN integration channel (server -> controller)
    # Messages are one JSON object per connection, newline terminated:
    #   {"cmd": "INSTALL", "client_id": "h1", "bandwidth": 200}
    #   {"cmd": "REMOVE",  "client_id": "h1"}
    # ------------------------------------------------------------------
    def _policy_listener(self):
        if os.path.exists(SDN_SOCKET_PATH):
            os.remove(SDN_SOCKET_PATH)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SDN_SOCKET_PATH)
        os.chmod(SDN_SOCKET_PATH, 0o666)
        srv.listen(10)
        print(f"[SDN Controller] Policy channel listening on {SDN_SOCKET_PATH}")
        while True:
            conn, _ = srv.accept()
            hub.spawn(self._handle_policy_conn, conn)

    def _handle_policy_conn(self, conn):
        try:
            data = conn.recv(4096).decode("utf-8").strip()
            req = json.loads(data)
            cmd = req.get("cmd")
            if cmd == "INSTALL":
                resp = self.install_reservation(req.get("client_id"), req.get("bandwidth"))
            elif cmd == "REMOVE":
                resp = self.remove_reservation(req.get("client_id"))
            else:
                resp = {"status": "ERROR", "reason": f"Unknown command {cmd}"}
        except Exception as e:
            resp = {"status": "ERROR", "reason": str(e)}
        try:
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        finally:
            conn.close()

