"""Offline, pure-numpy frame operations; no SLAM or fitted calibration."""
from pathlib import Path
import numpy as np

Q = np.array([[-1.,0,0,0],[0,0,1,0],[0,1,0,0],[0,0,0,1]])
TM = np.array([[1.0157,.1828,-.2389,.0113],[.0009,-.8431,-.6413,-.0098],[-.3009,.6147,-.8085,.0111],[0,0,0,1.]])
u,s,vt = np.linalg.svd(TM[:3,:3])
E = np.eye(4); E[:3,:3] = u @ np.diag([1,1,np.linalg.det(u@vt)]) @ vt
E[:3,3] = TM[:3,3]

def read(path):
    return np.array([list(map(float,l.split())) for l in Path(path).read_text().splitlines() if l.strip() and not l.lstrip().startswith('#')])

def quat_matrix(q):
    q = np.asarray(q,float); q = q/np.linalg.norm(q,axis=-1,keepdims=True)
    x,y,z,w = np.moveaxis(q,-1,0)
    out = np.empty(q.shape[:-1]+(3,3))
    out[...,0,0]=1-2*(y*y+z*z); out[...,0,1]=2*(x*y-z*w); out[...,0,2]=2*(x*z+y*w)
    out[...,1,0]=2*(x*y+z*w); out[...,1,1]=1-2*(x*x+z*z); out[...,1,2]=2*(y*z-x*w)
    out[...,2,0]=2*(x*z-y*w); out[...,2,1]=2*(y*z+x*w); out[...,2,2]=1-2*(x*x+y*y)
    return out

def poses(rows):
    out=np.tile(np.eye(4),(len(rows),1,1));out[:,:3,:3]=quat_matrix(rows[:,4:8]);out[:,:3,3]=rows[:,1:4]
    return rows[:,0],out

def corrected(g,variant='official_rigid'):
    if variant=='raw_file_negative': return g.copy()
    e=E.copy()
    if variant=='inverse_extrinsic_negative': e=np.linalg.inv(e)
    if variant=='zero_translation_sensitivity': e[:3,3]=0
    if variant=='translation_divide_scale_sensitivity': e[:3,3]/=s.mean()
    if variant=='ignore_ROS_negative': return g@e
    return Q @ g @ Q @ e

def interpolate(rows,t):
    ts=rows[:,0];j=np.searchsorted(ts,t)
    if j<len(ts) and abs(ts[j]-t)<1e-8: return poses(rows[j:j+1])[1][0]
    if j==0 or j==len(ts): raise ValueError('No extrapolation')
    a,b=rows[j-1],rows[j];f=(t-a[0])/(b[0]-a[0]);q0=a[4:8]/np.linalg.norm(a[4:8]);q1=b[4:8]/np.linalg.norm(b[4:8]);d=q0@q1
    if d<0: q1=-q1;d=-d
    if d>.9995: q=(1-f)*q0+f*q1
    else:
        angle=np.arccos(np.clip(d,-1,1));q=(np.sin((1-f)*angle)*q0+np.sin(f*angle)*q1)/np.sin(angle)
    h=np.eye(4);h[:3,:3]=quat_matrix(q);h[:3,3]=(1-f)*a[1:4]+f*b[1:4];return h

def associate(a,b,tolerance=.02):
    candidates=[]
    for i,t in enumerate(a):
        lo=np.searchsorted(b,t-tolerance,side='right'); hi=np.searchsorted(b,t+tolerance,side='left')
        candidates.extend((abs(t-b[j]),i,j) for j in range(lo,hi))
    ua,ub,out=set(),set(),[]
    for _,i,j in sorted(candidates):
        if i not in ua and j not in ub: ua.add(i);ub.add(j);out.append((i,j))
    return sorted(out)

def align(a,b):
    u,_,vt=np.linalg.svd((a-a.mean(0)).T@(b-b.mean(0)));d=np.eye(3);d[-1,-1]=np.linalg.det(vt.T@u.T);r=vt.T@d@u.T
    return r,b.mean(0)-r@a.mean(0)

def describe(x):
    x=np.asarray(x,float)
    if not len(x): return {'n':0}
    return {'n':len(x),'rmse':float(np.sqrt(np.mean(x*x))),'median':float(np.median(x)),'p90':float(np.quantile(x,.9)),'p95':float(np.quantile(x,.95)),'max':float(x.max())}

def angle(r): return np.degrees(np.arccos(np.clip((np.trace(r,axis1=-2,axis2=-1)-1)/2,-1,1)))
