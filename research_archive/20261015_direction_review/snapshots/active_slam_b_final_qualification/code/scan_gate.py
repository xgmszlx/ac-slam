#!/usr/bin/python3
"""Behavior-changing serialization of ORIGINAL packets; no GT, no scan editing."""
import argparse,io,hashlib,json,time,threading
from pathlib import Path
import rospy,tf2_ros
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from event_core import Journal,Sequencer
ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);a=ap.parse_args()
rospy.init_node('scan_gate');j=Journal(a.run/'gate_events.jsonl');seq=Sequencer(200);lock=threading.Lock();buf=tf2_ros.Buffer(rospy.Duration(60));listener=tf2_ros.TransformListener(buf)
pub=rospy.Publisher('/scan_ready',LaserScan,queue_size=20);errors=[]
def scan(m):
 b=io.BytesIO();m.serialize(b);raw=b.getvalue();ns=m.header.stamp.to_nsec()
 j.emit(ns,m.header.seq,'SENSOR_INPUT',sha256=hashlib.sha256(raw).hexdigest())
 with lock:
  try:seq.enqueue(ns,m.header.seq,raw);j.emit(ns,m.header.seq,'GATE_ENQUEUED',pending=len(seq.pending))
  except Exception as e:errors.append(str(e));j.emit(ns,m.header.seq,'GATE_REJECTED',reason=str(e))
def trace(m):
 x=json.loads(m.data)
 if x['event'] in ['MAIN_END','LASER_TF_FAIL','LOCK_DROP']:
  with lock:
   try:seq.complete(x['stamp_ns']);j.emit(x['stamp_ns'],x['seq'],'TERMINAL_ACK',terminal=x['event'])
   except ValueError as e:errors.append(str(e));j.emit(x['stamp_ns'],x['seq'],'ACK_ERROR',reason=str(e))
rospy.Subscriber('/scan',LaserScan,scan,queue_size=2000);rospy.Subscriber('/icp/trace',String,trace,queue_size=10000)
def ready(ns):
 stamp=rospy.Time(ns//1000000000,ns%1000000000)
 return pub.get_num_connections()>0 and buf.can_transform('wheel_odom','base_footprint',stamp) and buf.can_transform('base_footprint','base_laser_link',stamp)
try:
 while not rospy.is_shutdown():
  with lock:item=seq.next(ready)
  if item:
   ns,n,raw=item;j.emit(ns,n,'DISPATCH',sha256=hashlib.sha256(raw).hexdigest())
   # AnyMsg bypasses rospy's top-level Header.seq renumbering.
   packet=rospy.AnyMsg();packet._buff=raw;pub.publish(packet)
  time.sleep(.001)
finally:
 with lock:
  for ns,n,raw in seq.pending:j.emit(ns,n,'SHUTDOWN_PENDING')
  if seq.inflight:j.emit(seq.inflight[0],seq.inflight[1],'SHUTDOWN_INFLIGHT')
 (a.run/'gate_summary.json').write_text(json.dumps(dict(input=len(seq.seen),completed=len(seq.completed),pending=len(seq.pending),errors=errors),indent=2));j.close()
