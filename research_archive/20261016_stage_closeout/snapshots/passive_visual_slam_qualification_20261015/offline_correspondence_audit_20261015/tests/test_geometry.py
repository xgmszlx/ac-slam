import pathlib,sys,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'code'))
from geometry import *
K=np.array([[500.,0,320],[0,500,240],[0,0,1]])
X=backproject([420,290],2.,K);assert np.allclose(X,[.4,.2,2]);assert np.allclose(project(X,K),[420,290])
# Camera moves right by 0.1m: a fixed point must move left by 25 pixels at z=2m.
Twc1=np.eye(4);Twc2=np.eye(4);Twc2[0,3]=.1;T=np.linalg.inv(Twc2)@Twc1;P=np.array([0.,0.,2.]);assert np.allclose(project(transform(T,P),K),[295,240]);assert np.allclose(transform(np.linalg.inv(T),transform(T,P)),P)
# A truly moving point +0.2m is a physical match but violates a static-world prediction by 50 pixels.
moved=transform(T,P)+[.2,0,0];assert abs(np.linalg.norm(project(moved,K)-project(transform(T,P),K))-50)<1e-9
q=slerp([0,0,0,1],[0,0,1,0],.5);assert np.allclose(rotation(q)@np.array([1.,0,0]),[0,1,0],atol=1e-12)
assert np.allclose(rotation(slerp([0,0,0,1],[0,0,0,-1],.3)),np.eye(3))
rows=np.array([[10,0,0,0,0,0,0,1],[10.01,.1,0,0,0,0,0,1]])
t,gap=pose_at(rows,10.005);assert abs(t[0,3]-.05)<1e-9
try:pose_at(rows,9.);raise AssertionError('extrapolation allowed')
except AssertionError as e:assert 'no GT' in str(e)
print('PASS: backprojection, camera-frame transform sign, dynamic/static distinction, quaternion SLERP, interpolation/no extrapolation')
