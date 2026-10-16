from pathlib import Path
import ctypes as C,json
import numpy as np
from scipy.spatial.transform import Rotation,Slerp
P=Path(__file__).resolve().parents[1]
B=Path('/home/wcqw/lilocbench_amcl_validation_20261016')
D=C.POINTER(C.c_double);F=C.POINTER(C.c_float);I=C.POINTER(C.c_int)
def ptr(a):return a.ctypes.data_as(D)
class Native:
 def __init__(self):
  self.lib=C.CDLL(str(P/'build/native_probe.so'))
  self.lib.probe_map.argtypes=[C.c_char_p];self.lib.probe_map.restype=C.c_void_p
  self.lib.probe_size.argtypes=[C.c_void_p];self.lib.probe_size.restype=C.c_int
  self.lib.probe_arrays.argtypes=[C.c_void_p,I,D,D]
  self.lib.probe_prepare.argtypes=[C.c_int,F,C.c_float,C.c_float,C.c_float,C.c_float,D,D,D]
  self.lib.probe_score.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,D,D,C.c_double,D,D];self.lib.probe_score.restype=C.c_double
  self.map=self.lib.probe_map(str(B/'data/map/map_office.png').encode());n=self.lib.probe_size(self.map)
  state=np.empty(n,dtype=np.int32);dist=np.empty(n);meta=np.empty(5);self.lib.probe_arrays(self.map,state.ctypes.data_as(I),ptr(dist),ptr(meta))
  self.nx,self.ny=map(int,meta[:2]);self.scale,self.ox,self.oy=meta[2:];self.state=state.reshape(self.ny,self.nx);self.dist=dist.reshape(self.ny,self.nx)
 def prepare(self,r):
  raw=np.ascontiguousarray(np.load(P/'data'/f"{r['id']}.npz")['ranges'],dtype=np.float32);rr=np.empty(len(raw));bb=np.empty(len(raw));quat=np.array(r['laser_in_base_xyz_xyzw'][3:],dtype=float)
  self.lib.probe_prepare(len(raw),raw.ctypes.data_as(F),r['range_min'],r['range_max'],r['angle_min'],r['angle_increment'],ptr(quat),ptr(rr),ptr(bb));return rr,bb
 def native_score(self,r,pose,model,common=True):
  rr,bb=self.prepare(r);lp=np.array(r['laser_in_base_xyz_xyzw'][:2]);pos=np.ascontiguousarray(pose,dtype=float)
  return self.lib.probe_score(self.map,model,91 if model==0 and common else 100,len(rr),ptr(rr),ptr(bb),r['range_max'],ptr(pos),ptr(lp))
 def pz(self,r,poses,indices=None):
  rr,bb=self.prepare(r);idx=np.arange(0,len(rr),9) if indices is None else np.array(indices)
  good=(rr[idx]<r['range_max'])&~np.isnan(rr[idx]);idx=idx[good]
  q=np.asarray(poses,dtype=float).reshape(-1,3);tx,ty=r['laser_in_base_xyz_xyzw'][:2];c=np.cos(q[:,2]);s=np.sin(q[:,2]);x=q[:,0]+tx*c-ty*s;y=q[:,1]+tx*s+ty*c;yaw=np.arctan2(np.sin(q[:,2]),np.cos(q[:,2]))
  hitsx=x[:,None]+rr[idx]*np.cos(yaw[:,None]+bb[idx]);hitsy=y[:,None]+rr[idx]*np.sin(yaw[:,None]+bb[idx])
  mi=np.floor((hitsx-self.ox)/self.scale+.5).astype(int)+self.nx//2;mj=np.floor((hitsy-self.oy)/self.scale+.5).astype(int)+self.ny//2
  valid=(mi>=0)&(mi<self.nx)&(mj>=0)&(mj<self.ny);dist=np.full(mi.shape,2.);dist[valid]=self.dist[mj[valid],mi[valid]]
  prob=.95*np.exp(-dist*dist/(2*.2*.2))+.05/r['range_max'];return prob,idx,dist,hitsx,hitsy
 def scores(self,r,poses):
  pz,idx,_,_,_=self.pz(r,poses)
  return np.log(1.+np.sum(pz*pz*pz,axis=1)),np.sum(np.log(pz),axis=1)
def interpolate(file,time):
 a=np.loadtxt(file);t=a[:,0]
 if time<t[0] or time>t[-1]:return None,{'status':'UNAVAILABLE_no_extrapolation','first':float(t[0]),'last':float(t[-1])}
 j=int(np.searchsorted(t,time));lo=max(0,j-1);hi=min(j,len(t)-1)
 if lo==hi:rot=Rotation.from_quat(a[lo,4:8])
 else:rot=Slerp(t[[lo,hi]],Rotation.from_quat(a[[lo,hi],4:8]))([time])[0]
 pose=[float(np.interp(time,t,a[:,1])),float(np.interp(time,t,a[:,2])),float(rot.as_euler('ZYX')[0])]
 return pose,{'status':'INTERPOLATED_OR_EXACT','bracket_stamps':[float(t[lo]),float(t[hi])],'gap_s':float(t[hi]-t[lo]),'uses_after10s_bracket_only_for_inrange_time':False}
