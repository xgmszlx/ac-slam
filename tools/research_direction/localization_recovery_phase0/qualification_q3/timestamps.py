"""Bounded, planar, exact-request-time TF reconstruction; no GT or extrapolation."""
import bisect
import math
import time
from collections import defaultdict, deque

MAP_CHAIN = ('map', 'offset', 'odom', 'base_footprint', 'base_link')


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return [a[0] + c*b[0] - s*b[1], a[1] + s*b[0] + c*b[1], wrap(a[2]+b[2])]


def inverse(p):
    c, s = math.cos(p[2]), math.sin(p[2])
    return [-c*p[0]-s*p[1], s*p[0]-c*p[1], -p[2]]


def pose(t):
    x, y, z, w = t['quaternion']
    roll = math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))
    pitch = math.asin(max(-1., min(1., 2*(w*y-z*x))))
    if abs(roll)>1e-6 or abs(pitch)>1e-6:
        raise ValueError('Non-planar TF cannot be represented as SE(2)')
    return [t['translation'][0], t['translation'][1], math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))]


class TFHistory:
    def __init__(self, max_span=.15, cache_s=None, max_per_edge=4096):
        self.max_span, self.cache_s, self.max_per_edge = max_span, cache_s, max_per_edge
        self.times, self.values = defaultdict(list), defaultdict(list)
        self.static_values = {}
        self.conflicting_duplicates = 0

    def add(self, transform, static=False):
        edge = (transform['parent'].lstrip('/'), transform['child'].lstrip('/'))
        stamp = float(transform['stamp']); value = pose(transform)
        if static:
            self.static_values[edge]=value
            return
        ts, vs = self.times[edge], self.values[edge]
        i = bisect.bisect_left(ts, stamp)
        if i<len(ts) and abs(ts[i]-stamp)<1e-8:
            if any(abs(a-b)>1e-10 for a,b in zip(vs[i],value)):
                self.conflicting_duplicates += 1
            return  # first receipt, matching TF2 duplicate rejection; never invent latest
        ts.insert(i, stamp); vs.insert(i, value)
        if self.cache_s is not None:
            cut = max(bisect.bisect_left(ts, ts[-1]-self.cache_s), len(ts)-self.max_per_edge, 0)
            if cut: del ts[:cut]; del vs[:cut]

    def edge_at(self, edge, stamp):
        if edge in self.static_values:
            return list(self.static_values[edge]), {'edge':edge,'span_s':0.,'bracket':None,'static_topic':True}
        ts, vs = self.times.get(edge, []), self.values.get(edge, [])
        if not ts: return None, {'reason':'EDGE_ABSENT', 'edge':edge}
        i = bisect.bisect_left(ts, stamp)
        for j in (i, i-1):
            if 0<=j<len(ts) and abs(ts[j]-stamp)<1e-7:
                return list(vs[j]), {'edge':edge, 'span_s':0., 'bracket':[ts[j],ts[j]], 'interpolated':False}
        if i==0 or i==len(ts):
            return None, {'reason':'OUTSIDE_RECORDED_RANGE', 'edge':edge, 'range':[ts[0],ts[-1]]}
        a,b = ts[i-1],ts[i]; span=b-a
        if span>self.max_span+1e-8:
            return None, {'reason':'TF_BRACKET_TOO_WIDE', 'edge':edge, 'span_s':span}
        u=(stamp-a)/span; p,q=vs[i-1],vs[i]
        result=[p[0]+u*(q[0]-p[0]),p[1]+u*(q[1]-p[1]),wrap(p[2]+u*wrap(q[2]-p[2]))]
        return result, {'edge':edge, 'span_s':span, 'bracket':[a,b], 'interpolated':True}

    def resolve(self, stamp, chain=MAP_CHAIN):
        result=[0.,0.,0.]; metadata=[]
        for edge in zip(chain,chain[1:]):
            value, info = self.edge_at(edge,stamp); metadata.append(info)
            if value is None:return None, {'status':info['reason'], 'edges':metadata}
            result=compose(result,value)
        return result, {'status':'RESOLVED_EXACT_REQUEST_TIME', 'edges':metadata,
                        'max_span_s':max(x['span_s'] for x in metadata), 'requested_stamp':stamp,
                        'evaluation_stamp':stamp, 'latest_fallback':False}

    def latest_common_stamp(self, chain=MAP_CHAIN):
        edges=list(zip(chain,chain[1:]))
        if not all(self.times.get(e) or e in self.static_values for e in edges):return None
        dynamic=[self.times[e][-1] for e in edges if e not in self.static_values]
        return min(dynamic) if dynamic else None


class PendingScans:
    def __init__(self, capacity=200, timeout_s=2.):
        self.capacity, self.timeout_s = capacity, timeout_s
        self.items=deque()

    def add(self, item, wall):
        overflow=None
        if len(self.items)>=self.capacity:overflow=self.items.popleft()
        self.items.append((item,wall))
        return overflow

    def drain(self, resolver, wall):
        finished=[]; pending=deque()
        while self.items:
            item, received=self.items.popleft(); value, meta=resolver(item['stamp'])
            if value is not None:
                finished.append((item,value,meta,wall))
            elif wall-received>=self.timeout_s:
                finished.append((item,None,{**meta,'status':'WALL_QUEUE_TIMEOUT'},wall))
            else:pending.append((item,received))
        self.items=pending
        return finished


def wall_wait(predicate, timeout, alive=lambda:True, clock=time.monotonic, sleep=time.sleep):
    start=clock()
    while clock()-start<timeout:
        if not alive():raise RuntimeError('Required process/ROS stopped during readiness')
        if predicate():return clock()-start
        sleep(.02)
    raise TimeoutError('Wall-clock readiness timeout: %.3fs'%timeout)


def action_connected(client):
    """Read actual actionlib connections, without ROS-time timeout loops."""
    ac=client.action_client; status=ac.last_status_msg
    if status is None:return False
    server=status._connection_header.get('callerid')
    return bool(server and ac.pub_goal.impl.has_connection(server) and ac.pub_cancel.impl.has_connection(server)
                and any(c.callerid_pub==server for c in ac.result_sub.impl.connections)
                and any(c.callerid_pub==server for c in ac.feedback_sub.impl.connections))
