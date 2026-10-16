from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation,Slerp
P=Path(__file__).resolve().parents[1];B=Path('/home/wcqw/lilocbench_amcl_validation_20261016');R=Path('/home/wcqw/lilocbench_amcl_recovery_control_20261016');L=Path('/home/wcqw/lilocbench_likelihood_audit_20261016')
def wrap(x):return np.arctan2(np.sin(x),np.cos(x))
def interp(a,t):
 times=a[:,0]
 if t<times[0] or t>times[-1]:raise ValueError('No time extrapolation allowed')
 j=int(np.searchsorted(times,t));lo=max(0,j-1);hi=min(j,len(a)-1)
 rot=Slerp(times[[lo,hi]],Rotation.from_quat(a[[lo,hi],4:8]))([t])[0] if lo!=hi else Rotation.from_quat(a[lo,4:8]);pose=np.array([np.interp(t,times,a[:,1]),np.interp(t,times,a[:,2]),rot.as_euler('ZYX')[0]])
 return pose,lo,hi
def pose_row(row):return np.r_[row[1:3],Rotation.from_quat(row[4:8]).as_euler('ZYX')[0]]
