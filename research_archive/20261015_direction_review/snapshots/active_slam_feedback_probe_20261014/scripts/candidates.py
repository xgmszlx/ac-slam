"""Online-map-only route certification and geometric proxies. No truth inputs."""
import heapq
import math
import numpy as np
from scipy import ndimage

FOOTPRINT=[[-.313,-.2525],[-.313,.2525],[.313,.2525],[.313,-.2525]]
RADIUS=math.hypot(.313,.2525)+.10

class Grid:
    def __init__(self,record,start=None):
        self.res=record['resolution'];self.origin=record['origin'];self.data=np.asarray(record['data'],dtype=np.int16).reshape(record['height'],record['width'])
        if abs(self.origin[2])>1e-8:raise ValueError('Rotated map origin not supported')
        self.free=self.data==0
        self.distance=ndimage.distance_transform_edt(self.free)*self.res
        self.safe=self.free & (self.distance>=RADIUS)
        if start is not None:
            y,x=self.cell(start);labels,_=ndimage.label(self.safe,np.ones((3,3)))
            if not self.inside(y,x) or labels[y,x]==0:raise ValueError('Robot start not footprint-safe in online map')
            self.safe &= labels==labels[y,x]
        occupancy=(self.data>=50).astype(float)
        smooth=ndimage.gaussian_filter(occupancy,1.)
        self.nx=ndimage.sobel(smooth,axis=1);self.ny=ndimage.sobel(smooth,axis=0)
    def cell(self,p):return int(math.floor((p[1]-self.origin[1])/self.res)),int(math.floor((p[0]-self.origin[0])/self.res))
    def point(self,c):return [self.origin[0]+(c[1]+.5)*self.res,self.origin[1]+(c[0]+.5)*self.res]
    def inside(self,y,x):return 0<=y<self.data.shape[0] and 0<=x<self.data.shape[1]
    def astar(self,start,goal):
        a,b=self.cell(start),self.cell(goal)
        if not all(self.inside(*c) and self.safe[c] for c in [a,b]):return None
        q=[(0.,a)];cost={a:0.};parent={a:None};closed=set()
        while q:
            _,p=heapq.heappop(q)
            if p in closed:continue
            if p==b:
                route=[]
                while p is not None:route.append(self.point(p));p=parent[p]
                return route[::-1]
            closed.add(p)
            if len(closed)>250000:return None
            for dy,dx in [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,1),(1,-1),(-1,-1)]:
                v=(p[0]+dy,p[1]+dx)
                if not self.inside(*v) or not self.safe[v]:continue
                if dy and dx and (not self.safe[p[0]+dy,p[1]] or not self.safe[p[0],p[1]+dx]):continue
                d=cost[p]+math.hypot(dy,dx)
                if d<cost.get(v,float('inf')):
                    cost[v]=d;parent[v]=p
                    heapq.heappush(q,(d+math.hypot(v[0]-b[0],v[1]-b[1]),v))
        return None
    def frontier_approach(self,proposal):
        cells=np.argwhere(self.safe)
        if not len(cells):return None
        xs=self.origin[0]+(cells[:,1]+.5)*self.res;ys=self.origin[1]+(cells[:,0]+.5)*self.res
        i=int(np.argmin((xs-proposal[0])**2+(ys-proposal[1])**2))
        return [float(xs[i]),float(ys[i])]
    def proxy(self,p,yaw):
        # 181 directions, physical 180-degree FOV/range; unknown terminates a ray.
        angles=np.linspace(yaw-math.pi/2,yaw+math.pi/2,181)
        origin=np.array(p[:2])+ .2*np.array([math.cos(yaw),math.sin(yaw)])
        dirs=np.stack([np.cos(angles),np.sin(angles)],axis=1)
        active=np.ones(len(angles),bool);hits=[];unknown=0
        for d in np.arange(self.res/2,25.,self.res/2):
            pos=origin+d*dirs;xs=np.floor((pos[:,0]-self.origin[0])/self.res).astype(int);ys=np.floor((pos[:,1]-self.origin[1])/self.res).astype(int)
            valid=active&(xs>=0)&(ys>=0)&(xs<self.data.shape[1])&(ys<self.data.shape[0])
            unknown+=int(np.sum(active&~valid));active&=valid
            inds=np.flatnonzero(active)
            if not len(inds):break
            values=self.data[ys[inds],xs[inds]]
            un=inds[values<0];unknown+=len(un);active[un]=False
            occ=inds[values>=50]
            for i in occ:
                n=np.array([self.nx[ys[i],xs[i]],self.ny[ys[i],xs[i]]]);norm=np.linalg.norm(n)
                if norm>1e-8:hits.append((pos[i]-np.array(p[:2]),n/norm))
            active[occ]=False
        if not hits:return {'translation_weak':None,'pose_weak':None,'known_hits':0,'unknown_terminated':unknown,'hit_fraction':0.}
        ns=np.array([n for _,n in hits]);ht=ns.T@ns
        # yaw column normalized by fixed 1 m scale. This is a proxy, not covariance.
        js=np.array([[n[0],n[1],n[0]*(-v[1])+n[1]*v[0]] for v,n in hits]);h=js.T@js
        return {'translation_weak':float(np.linalg.eigvalsh(ht)[0]/np.trace(ht)),
                'pose_weak':float(np.linalg.eigvalsh(h)[0]/np.trace(h)),
                'known_hits':len(hits),'unknown_terminated':int(unknown),'hit_fraction':len(hits)/181.}

def length(path):return sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(path,path[1:]))
def sample(path,spacing=.5):
    out=[path[0]];travel=0.
    for a,b in zip(path,path[1:]):
        travel+=math.dist(a,b)
        if travel>=spacing:out.append(b);travel=0.
    if out[-1]!=path[-1]:out.append(path[-1])
    return out
def route_metrics(grid,path):
    pts=sample(path);values=[]
    for i,p in enumerate(pts):
        a,b=(pts[i],pts[min(i+1,len(pts)-1)]) if i<len(pts)-1 else (pts[max(0,i-1)],pts[i])
        yaw=math.atan2(b[1]-a[1],b[0]-a[0]);values.append({'position':p,'yaw':yaw,**grid.proxy(p,yaw)})
    good=[v['translation_weak'] for v in values if v['translation_weak'] is not None]
    return {'length_m':length(path),'minimum_clearance_m':min(grid.distance[grid.cell(p)] for p in path),
            'translation_weak_mean':float(np.mean(good)) if good else None,'prediction_samples':values}
def certify_pair(record,start,proposals):
    grid=Grid(record,start);rejections=[]
    for proposal in proposals[:12]:
        goal=grid.frontier_approach(proposal);a=grid.astar(start,goal) if goal else None
        if not a or length(a)<3 or length(a)>12:
            rejections.append({'proposal':proposal,'reason':'NO_SAFE_3_TO_12_M_BASE_PATH'});continue
        av=route_metrics(grid,a)
        for fraction in [.5,.3,.7]:
            idx=int((len(a)-1)*fraction);p=a[idx];lo=a[max(0,idx-2)];hi=a[min(len(a)-1,idx+2)]
            yaw=math.atan2(hi[1]-lo[1],hi[0]-lo[0]);normal=[-math.sin(yaw),math.cos(yaw)]
            for offset in [.5,-.5,1.,-1.,2.,-2.]:
                via=[p[0]+offset*normal[0],p[1]+offset*normal[1]]
                left,right=grid.astar(start,via),grid.astar(via,goal)
                if not left or not right:continue
                b=left+right[1:];ratio=length(b)/length(a)
                if ratio>1.20:continue
                separation=max(min(math.dist(p,q) for q in sample(a)) for p in sample(b))
                if separation<.45:continue
                bv=route_metrics(grid,b)
                if av['translation_weak_mean'] is None or bv['translation_weak_mean'] is None:continue
                difference=abs(av['translation_weak_mean']-bv['translation_weak_mean'])
                if difference<.03:
                    rejections.append({'proposal':proposal,'via':via,'reason':'GEOMETRIC_PREDICTION_DIFFERENCE_LT_0_03','difference':difference,'length_ratio':ratio});continue
                return {'status':'NOMINAL_MAP_CERTIFIED_CONTROLLER_NOT_YET_CERTIFIED','goal':goal,'start':start,'length_ratio':ratio,'separation_m':separation,'geometry_difference':difference,
                  'A':{'path':a,**av},'B':{'path':b,'via':via,**bv},'rejections':rejections}
    return {'status':'NO_ACTION_CHOICE_SPACE','rejections':rejections,'safe_cell_count':int(np.sum(grid.safe)),'input_source':'DECISION_PRE_ONLINE_OCCUPANCY_ONLY'}
