#!/usr/bin/env python3
"""B1: conventional bounded correlative scan-to-map re-estimation, causal bag replay.

Not Olson's exact implementation; an explicitly disclosed baseline adaptation.
No GT enters the estimator. No new physical observations or actions.
"""
import argparse,copy,json,math,time
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
import rospy,rosbag
from rosgraph_msgs.msg import Clock
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import PoseWithCovarianceStamped,TransformStamped
from tf2_msgs.msg import TFMessage
from time_geometry import compose,inverse
R=Path(__file__).resolve().parents[1]
CFG=dict(xy_search_halfwidth_m=2.,coarse_xy_step_m=.1,yaw_halfwidth_rad=.2,coarse_yaw_step_rad=.05,refine_xy_halfwidth_m=.1,refine_xy_step_m=.025,refine_yaw_halfwidth_rad=.05,refine_yaw_step_rad=.0125,distance_cap_m=.5,max_sampled_beams=181,reestimate_every_scans=5,input_scope='causal current scan, prior occupancy, received baseline pose and wheel odometry; no GT',parameter_selection='frozen once after B0 failures; no tuning or independent efficacy claim')
ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('run');args=ap.parse_args();source=Path(args.source);run=Path(args.run)
f=R/'protocol/passive_frozen.json'
if f.exists():assert json.loads(f.read_text())==CFG
else:f.write_text(json.dumps(CFG,indent=2))
def p2(p):
    q=p.orientation;return [p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))]
scans=[];odoms={};gts={};poses=[];prior=None
with rosbag.Bag(str(source/'raw.bag')) as bag:
    for topic,msg,t in bag.read_messages():
        if topic=='/scan':scans.append(msg)
        elif topic=='/odom':odoms[msg.header.stamp.to_nsec()]=msg
        elif topic=='/base_pose_ground_truth':gts[msg.header.stamp.to_nsec()]=msg  # publish only for evaluator
        elif topic=='/amcl_pose':poses.append((t.to_sec(),msg))
        elif topic=='/prior_map':prior=msg
poses.sort(key=lambda a:a[0]);grid=np.array(prior.data).reshape(prior.info.height,prior.info.width)==100;dist=distance_transform_edt(~grid)*prior.info.resolution
origin=np.array([prior.info.origin.position.x,prior.info.origin.position.y]);res=prior.info.resolution
def match(scan,center):
    r=np.array(scan.ranges);angles=scan.angle_min+np.arange(len(r))*scan.angle_increment;ok=np.isfinite(r)&(r<18)&(r>scan.range_min)
    xy=np.c_[r[ok]*np.cos(angles[ok]),r[ok]*np.sin(angles[ok])];xy=xy[::max(1,int(math.ceil(len(xy)/181)))]
    def search(c,hxy,step,hyaw,astep):
        aa=np.arange(-hxy,hxy+step/2,step);xx,yy=np.meshgrid(aa,aa);positions=np.c_[xx.ravel(),yy.ravel()]+c[:2];best=(float('inf'),None)
        for yaw in c[2]+np.arange(-hyaw,hyaw+astep/2,astep):
            rot=np.array([[np.cos(yaw),-np.sin(yaw)],[np.sin(yaw),np.cos(yaw)]]);points=positions[:,None,:]+(xy@rot.T)[None,:,:]
            ij=np.floor((points-origin)/res).astype(int);valid=(ij[:,:,0]>=0)&(ij[:,:,0]<grid.shape[1])&(ij[:,:,1]>=0)&(ij[:,:,1]<grid.shape[0]);d=dist[np.clip(ij[:,:,1],0,grid.shape[0]-1),np.clip(ij[:,:,0],0,grid.shape[1]-1)];d=np.where(valid,d,.5)
            costs=np.minimum(d,.5)**2;cost=costs.mean(1)+1e-9*np.sum((positions-c[:2])**2,axis=1);k=int(cost.argmin())
            if float(cost[k])<best[0]:best=(float(cost[k]),np.r_[positions[k],yaw])
        return best
    cost,p=search(np.array(center),2.,.1,.2,.05);cost,p=search(p,.1,.025,.05,.0125);return p.tolist(),cost
rospy.init_node('passive_b1_player');pubscan=rospy.Publisher('/scan',LaserScan,queue_size=1);pubodom=rospy.Publisher('/odom',Odometry,queue_size=1);pubgt=rospy.Publisher('/base_pose_ground_truth',Odometry,queue_size=1);pubtf=rospy.Publisher('/tf',TFMessage,queue_size=10);pubclock=rospy.Publisher('/clock',Clock,queue_size=1);pubpose=rospy.Publisher('/amcl_pose',PoseWithCovarianceStamped,queue_size=1)
time.sleep(1);offset=None;pose_index=-1;baseline=PoseWithCovarianceStamped();baseline.pose.pose.position.x=-3.;baseline.pose.pose.position.y=-2.;baseline.pose.pose.orientation.w=1.;est=[];last_wheel=None
def recovery(msg):
    global offset
    if last_wheel is not None:offset=compose(p2(msg.pose.pose),inverse(last_wheel))
sub=rospy.Subscriber('/initialpose',PoseWithCovarianceStamped,recovery,queue_size=1)
def transform(parent,child,p,stamp,z=0.):
    t=TransformStamped();t.header.stamp=stamp;t.header.frame_id=parent;t.child_frame_id=child;t.transform.translation.x=p[0];t.transform.translation.y=p[1];t.transform.translation.z=z;t.transform.rotation.z=math.sin(p[2]/2);t.transform.rotation.w=math.cos(p[2]/2);return t
for i,scan in enumerate(scans):
    if rospy.is_shutdown():break
    n=scan.header.stamp.to_nsec();stamp=scan.header.stamp;ts=stamp.to_sec();odom=odoms[n];last_wheel=p2(odom.pose.pose)
    # Only baseline observations received by this scan's recorded timestamp enter the prior center.
    while pose_index+1<len(poses) and poses[pose_index+1][0]<=ts:pose_index+=1;baseline=poses[pose_index][1]
    pubclock.publish(Clock(stamp))
    if i%5==0 or offset is None:
        tic=time.monotonic();corrected,cost=match(scan,p2(baseline.pose.pose));compute=time.monotonic()-tic;offset=compose(corrected,inverse(last_wheel));est.append(dict(stamp=ts,pose=corrected,cost=cost,compute_wall_s=compute))
    current=compose(offset,last_wheel)
    pubtf.publish(TFMessage([transform('map','odom',offset,stamp),transform('odom','base_footprint',last_wheel,stamp),transform('base_footprint','base_link',[0,0,0],stamp),transform('base_link','base_laser_link',[0,0,0],stamp,.2)]))
    pm=PoseWithCovarianceStamped();pm.header.stamp=stamp;pm.header.frame_id='map';pm.pose.pose.position.x=current[0];pm.pose.pose.position.y=current[1];pm.pose.pose.orientation.z=math.sin(current[2]/2);pm.pose.pose.orientation.w=math.cos(current[2]/2);pubpose.publish(pm)
    pubodom.publish(odom)
    if n in gts:pubgt.publish(gts[n])
    time.sleep(.04);pubscan.publish(scan);time.sleep(.06)
(run/'passive_estimates.json').write_text(json.dumps(est,indent=2))
# Flush through collector deadline without adding physical observations.
for j in range(60):pubclock.publish(Clock(rospy.Time.from_sec(ts+.1*(j+1))));time.sleep(.1)
