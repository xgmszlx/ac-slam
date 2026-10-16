"""OFFLINE_DIAGNOSTIC pinhole/GT geometry; not an online estimator."""
import numpy as np

def rotation(q):
 x,y,z,w=np.asarray(q,float)/np.linalg.norm(q)
 return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def slerp(a,b,t):
 a=np.asarray(a,float)/np.linalg.norm(a);b=np.asarray(b,float)/np.linalg.norm(b);dot=float(a@b)
 if dot<0:b=-b;dot=-dot
 dot=min(1.,max(-1.,dot))
 if dot>.9995:q=(1-t)*a+t*b;return q/np.linalg.norm(q)
 angle=np.arccos(dot);return (np.sin((1-t)*angle)*a+np.sin(t*angle)*b)/np.sin(angle)
def pose_at(rows,t):
 j=int(np.searchsorted(rows[:,0],t));assert 0<j<len(rows),'no GT extrapolation'
 a,b=rows[j-1],rows[j];assert b[0]-a[0]<=.02,'GT bracket gap too large'
 u=(t-a[0])/(b[0]-a[0]);T=np.eye(4);T[:3,:3]=rotation(slerp(a[4:8],b[4:8],u));T[:3,3]=(1-u)*a[1:4]+u*b[1:4]
 return T,float(b[0]-a[0])
def backproject(xy,z,K):
 return np.array([(xy[0]-K[0,2])*z/K[0,0],(xy[1]-K[1,2])*z/K[1,1],z])
def transform(T,X):return T[:3,:3]@X+T[:3,3]
def project(X,K):return np.array([K[0,0]*X[0]/X[2]+K[0,2],K[1,1]*X[1]/X[2]+K[1,2]])
def angle_deg(R):return float(np.arccos(np.clip((np.trace(R)-1)/2,-1,1))*180/np.pi)
