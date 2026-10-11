import json
import os

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER, DEAD_DISPATCHER,
                                    set_ev_cls)
from ryu.ofproto import ofproto_v1_3
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib import hub
from webob import Response

TOPO_FILE = os.environ.get(
    'TOPO_FILE',
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  '..', 'topology', 'topology.json')))

# Best-effort static routes (primary path via s2): dpid -> {dst_ip: out_port}
BASE_ROUTES = {
    1: {'10.0.0.1': 1, '10.0.0.2': 2, '10.0.0.3': 3, '10.0.0.4': 3},
    2: {'10.0.0.1': 1, '10.0.0.2': 1, '10.0.0.3': 2, '10.0.0.4': 2},
    3: {'10.0.0.1': 1, '10.0.0.2': 1, '10.0.0.3': 2, '10.0.0.4': 2},
    4: {'10.0.0.1': 3, '10.0.0.2': 3, '10.0.0.3': 1, '10.0.0.4': 2},
}


class PolicyError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


class Topo:
    """Loads topology.json (Contract A)."""

    def __init__(self, path):
        with open(path) as f:
            t = json.load(f)
        self.dpid = {n: int(d) for n, d in t['switch_dpid'].items()}
        self.hosts = {}      # ip -> (dpid, port)
        self.ports = {d: set() for d in self.dpid.values()}
        for h in t['hosts'].values():
            d = self.dpid[h['switch']]
            self.hosts[h['ip']] = (d, h['port'])
            self.ports[d].add(h['port'])
        self.peer = {}       # (dpid, port) -> (dpid, port) at the other end
        self.link_of = {}    # (dpid, port) -> (link_key, capacity_kbps)
        for l in t['links']:
            a, b = self.dpid[l['a']], self.dpid[l['b']]
            key = '%s-%s' % (l['a'], l['b'])
            cap = int(l['capacity_mbps']) * 1000
            self.peer[(a, l['a_port'])] = (b, l['b_port'])
            self.peer[(b, l['b_port'])] = (a, l['a_port'])
            self.link_of[(a, l['a_port'])] = (key, cap)
            self.link_of[(b, l['b_port'])] = (key, cap)
            self.ports[a].add(l['a_port'])
            self.ports[b].add(l['b_port'])


class ReservationApp(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.topo = Topo(TOPO_FILE)
        self.datapaths = {}    # dpid -> datapath
        self.policies = {}     # id -> {'hops', 'rate_kbps', 'links'}
        self.ledger = {}       # link_key -> reserved kbps
        self.port_stats = {}   # dpid -> port -> counters
        kwargs['wsgi'].register(RestAPI, {'app': self})
        hub.spawn(self._poll_stats)

    # ---------- switch lifecycle ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch(self, ev):
        dp = ev.msg.datapath
        ofp, p = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        # start clean: remove old flows and meters
        dp.send_msg(p.OFPFlowMod(datapath=dp, table_id=ofp.OFPTT_ALL,
                                 command=ofp.OFPFC_DELETE,
                                 out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))
        dp.send_msg(p.OFPMeterMod(dp, ofp.OFPMC_DELETE, ofp.OFPMF_KBPS,
                                  ofp.OFPM_ALL))
        # table-miss
        self._add_flow(dp, 0, p.OFPMatch(),
                       [p.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)])
        # best-effort base rules, priority 10
        for ip, port in BASE_ROUTES.get(dp.id, {}).items():
            self._add_flow(dp, 10,
                           p.OFPMatch(eth_type=0x0800, ipv4_dst=ip),
                           [p.OFPActionOutput(port)])
        self.logger.info('Switch connected: %s', dp.id)

    @set_ev_cls(ofp_event.EventOFPStateChange, DEAD_DISPATCHER)
    def on_dead(self, ev):
        dp = ev.datapath
        if dp is not None and dp.id in self.datapaths:
            del self.datapaths[dp.id]
            self.logger.info('Switch disconnected: %s', dp.id)

    def _add_flow(self, dp, priority, match, actions, cookie=0):
        ofp, p = dp.ofproto, dp.ofproto_parser
        inst = [p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, cookie=cookie,
                                 priority=priority, match=match,
                                 instructions=inst))

    # ---------- validation (V4) ----------
    def validate(self, body):
        t = self.topo
        # 1) format -> 400
        if not isinstance(body, dict):
            raise PolicyError(400, 'body must be a JSON object')
        for k in ('id', 'src_ip', 'dst_ip', 'rate_kbps', 'hops'):
            if k not in body:
                raise PolicyError(400, 'missing field: %s' % k)
        pid, rate, hops = body['id'], body['rate_kbps'], body['hops']
        if not _is_int(pid) or not (1 <= pid < 0xffff0000):
            raise PolicyError(400, 'id must be an integer >= 1')
        if not _is_int(rate) or rate <= 0:
            raise PolicyError(400, 'rate_kbps must be an integer > 0')
        src, dst = body['src_ip'], body['dst_ip']
        if src not in t.hosts or dst not in t.hosts:
            raise PolicyError(400, 'unknown src_ip or dst_ip')
        if src == dst:
            raise PolicyError(400, 'src_ip equals dst_ip')
        if not isinstance(hops, list) or not hops:
            raise PolicyError(400, 'hops must be a non-empty list')
        for h in hops:
            if not isinstance(h, dict) or not all(
                    _is_int(h.get(k)) for k in ('dpid', 'in_port', 'out_port')):
                raise PolicyError(400, 'each hop needs integer dpid, in_port, out_port')
        # 2) switches connected -> 400
        for h in hops:
            if h['dpid'] not in self.datapaths:
                raise PolicyError(400, 'switch %d is not connected' % h['dpid'])
        if len({h['dpid'] for h in hops}) != len(hops):
            raise PolicyError(400, 'path visits a switch twice')
        # 3) hops consistent with topology -> 400
        for h in hops:
            for k in ('in_port', 'out_port'):
                if h[k] not in t.ports[h['dpid']]:
                    raise PolicyError(400, 'port %d does not exist on switch %d'
                                      % (h[k], h['dpid']))
        if (hops[0]['dpid'], hops[0]['in_port']) != t.hosts[src]:
            raise PolicyError(400, 'first hop does not match the source host attachment')
        if (hops[-1]['dpid'], hops[-1]['out_port']) != t.hosts[dst]:
            raise PolicyError(400, 'last hop does not match the destination host attachment')
        for a, b in zip(hops, hops[1:]):
            if t.peer.get((a['dpid'], a['out_port'])) != (b['dpid'], b['in_port']):
                raise PolicyError(400, 'hops %d -> %d do not follow a real link'
                                  % (a['dpid'], b['dpid']))
        # 4) duplicate id -> 409
        if pid in self.policies:
            raise PolicyError(409, 'reservation id %d already installed' % pid)
        # 5) ledger capacity -> 409
        links = []
        for h in hops[:-1]:
            key, cap = t.link_of[(h['dpid'], h['out_port'])]
            if self.ledger.get(key, 0) + rate > cap:
                raise PolicyError(409, 'link %s would exceed capacity (%d kbps)'
                                  % (key, cap))
            links.append(key)
        return links

    # ---------- install / remove ----------
    def add_policy(self, body):
        links = self.validate(body)          # raises PolicyError, installs nothing
        pid, rate, hops = body['id'], body['rate_kbps'], body['hops']
        src, dst = body['src_ip'], body['dst_ip']
        for hop in hops:
            dp = self.datapaths[hop['dpid']]
            ofp, p = dp.ofproto, dp.ofproto_parser
            # meter (rate limiter); meter id = reservation id
            band = p.OFPMeterBandDrop(rate=rate, burst_size=max(rate // 10, 100))
            dp.send_msg(p.OFPMeterMod(dp, ofp.OFPMC_ADD, ofp.OFPMF_KBPS,
                                      pid, [band]))
            # forward flow with meter
            match = p.OFPMatch(eth_type=0x0800, ipv4_src=src, ipv4_dst=dst)
            inst = [p.OFPInstructionMeter(pid),
                    p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                            [p.OFPActionOutput(hop['out_port'])])]
            dp.send_msg(p.OFPFlowMod(datapath=dp, cookie=pid, priority=100,
                                     match=match, instructions=inst))
            # reverse flow (TCP ACKs / replies), no meter
            rmatch = p.OFPMatch(eth_type=0x0800, ipv4_src=dst, ipv4_dst=src)
            self._add_flow(dp, 100, rmatch,
                           [p.OFPActionOutput(hop['in_port'])], cookie=pid)
        for key in links:
            self.ledger[key] = self.ledger.get(key, 0) + rate
        self.policies[pid] = {'src_ip': src, 'dst_ip': dst, 'rate_kbps': rate,
                              'hops': hops, 'links': links}
        self.logger.info('Policy %d installed: %s -> %s @ %d kbps',
                         pid, src, dst, rate)

    def remove_policy(self, pid):
        pol = self.policies.pop(pid, None)
        if pol is None:
            return False
        for hop in pol['hops']:
            dp = self.datapaths.get(hop['dpid'])
            if dp is None:
                continue
            ofp, p = dp.ofproto, dp.ofproto_parser
            dp.send_msg(p.OFPFlowMod(datapath=dp, cookie=pid,
                                     cookie_mask=0xffffffffffffffff,
                                     table_id=ofp.OFPTT_ALL,
                                     command=ofp.OFPFC_DELETE,
                                     out_port=ofp.OFPP_ANY,
                                     out_group=ofp.OFPG_ANY))
            dp.send_msg(p.OFPMeterMod(dp, ofp.OFPMC_DELETE, ofp.OFPMF_KBPS, pid))
        for key in pol['links']:
            self.ledger[key] = max(0, self.ledger.get(key, 0) - pol['rate_kbps'])
        self.logger.info('Policy %d removed', pid)
        return True

    # ---------- port stats (V7) ----------
    def _poll_stats(self):
        while True:
            for dp in list(self.datapaths.values()):
                p = dp.ofproto_parser
                dp.send_msg(p.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
            hub.sleep(1)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, 'main')
    def on_port_stats(self, ev):
        dpid = ev.msg.datapath.id
        table = self.port_stats.setdefault(dpid, {})
        for st in ev.msg.body:
            if st.port_no >= 0xffffff00:      # skip LOCAL etc.
                continue
            table[st.port_no] = {'tx_bytes': st.tx_bytes, 'rx_bytes': st.rx_bytes,
                                 'tx_packets': st.tx_packets,
                                 'rx_packets': st.rx_packets}


def _json(status, obj):
    return Response(content_type='application/json', status=status,
                    body=json.dumps(obj).encode('utf-8'))


class RestAPI(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app = data['app']

    @route('policy_add', '/policy', methods=['POST'])
    def add_policy(self, req, **kw):
        try:
            body = json.loads(req.body.decode('utf-8'))
        except Exception:
            return _json(400, {'error': 'invalid JSON'})
        try:
            self.app.add_policy(body)
        except PolicyError as e:
            return _json(e.status, {'error': e.msg})
        except Exception as e:
            return _json(500, {'error': 'internal error: %s' % e})
        return _json(200, {'status': 'installed', 'id': body['id']})

    @route('policy_del', '/policy/{pid}', methods=['DELETE'])
    def del_policy(self, req, pid, **kw):
        try:
            pid = int(pid)
        except ValueError:
            return _json(400, {'error': 'id must be an integer'})
        if not self.app.remove_policy(pid):
            return _json(404, {'error': 'unknown policy id'})
        return _json(200, {'status': 'removed', 'id': pid})

    @route('policy_list', '/policy', methods=['GET'])
    def list_policy(self, req, **kw):
        return _json(200, {'policies': {str(k): v for k, v in self.app.policies.items()},
                           'ledger_kbps': self.app.ledger})

    @route('switches', '/switches', methods=['GET'])
    def switches(self, req, **kw):
        return _json(200, {'switches': sorted(self.app.datapaths.keys())})

    @route('stats', '/stats/ports', methods=['GET'])
    def stats(self, req, **kw):
        return _json(200, {str(d): {str(p): c for p, c in ports.items()}
                           for d, ports in self.app.port_stats.items()})
