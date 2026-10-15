import unittest,sys,tempfile,threading,json,io,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from event_core import Sequencer,Journal,SingleWriter
from time_geometry import TFHistory,compose,inverse
class Events(unittest.TestCase):
 def test_burst_identity_and_no_concurrent_dispatch(self):
  s=Sequencer(100)
  for i in range(100):s.enqueue(i+1,i,bytes([i]))
  for i in range(100):
   x=s.next(lambda ns:True);self.assertEqual(x,(i+1,i,bytes([i])));self.assertIsNone(s.next(lambda ns:True));s.complete(i+1)
  self.assertEqual(len(s.completed),100)
 def test_tf_gate_does_not_skip_pending(self):
  s=Sequencer();s.enqueue(10,2,b'x');self.assertIsNone(s.next(lambda ns:False));self.assertEqual(s.next(lambda ns:True),(10,2,b'x'))
 def test_wrong_ack_rejected(self):
  s=Sequencer();s.enqueue(10,2,b'x');s.next(lambda ns:True)
  with self.assertRaises(ValueError):s.complete(11)
 def test_bounded_overflow_explicit(self):
  s=Sequencer(1);s.enqueue(10,1,b'a')
  with self.assertRaises(OverflowError):s.enqueue(20,2,b'b')
 def test_duplicate_identity_rejected(self):
  s=Sequencer();s.enqueue(10,1,b'a')
  with self.assertRaises(ValueError):s.enqueue(10,2,b'b')
 def test_single_writer_with_service_and_concurrent_callbacks(self):
  writers=set();items=[]
  def write(x):writers.add(threading.get_ident());items.append(x)
  w=SingleWriter(write);ts=[threading.Thread(target=lambda j=j:[w.put((j,i)) for i in range(100)]) for j in range(8)]
  for t in ts:t.start()
  for t in ts:t.join()
  w.put(('service',0));w.seal();self.assertEqual(len(writers),1);self.assertEqual(len(set(items)),801)
  with self.assertRaises(RuntimeError):w.put('late')
 def test_concurrent_json_journal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'events';j=Journal(p);ts=[threading.Thread(target=lambda k=k:[j.emit(i,k,'x') for i in range(50)]) for k in range(8)]
   for t in ts:t.start()
   for t in ts:t.join()
   j.close();self.assertEqual(len([json.loads(x) for x in p.read_text().splitlines()]),400)
 def test_anymsg_preserves_full_laserscan_bytes(self):
  import rospy
  from sensor_msgs.msg import LaserScan
  from rospy.msg import serialize_message
  s=LaserScan();s.header.seq=73;s.header.stamp=rospy.Time(123,999999999);s.header.frame_id='laser';s.ranges=[1.,2.,3.]
  raw=io.BytesIO();s.serialize(raw);a=rospy.AnyMsg();a._buff=raw.getvalue();b=io.BytesIO();serialize_message(b,999,a)
  self.assertEqual(b.getvalue()[4:],raw.getvalue());self.assertEqual(s.header.seq,73)
 def test_tf_exact_interpolation_and_no_extrapolation(self):
  h=TFHistory(max_span=.15)
  for t,x in [(1,0),(1.1,1)]:h.add(dict(parent='map',child='odom',stamp=t,translation=[x,0,0],quaternion=[0,0,0,1]))
  self.assertAlmostEqual(h.edge_at(('map','odom'),1.05)[0][0],.5);self.assertIsNone(h.edge_at(('map','odom'),.9)[0])
  self.assertIsNone(h.edge_at(('map','odom'),1.2)[0])
 def test_GT_anchor_and_coordinate_inverse(self):
  p=compose([3,2,0],[-3,-2,0]);self.assertEqual(p,[0,0,0]);self.assertEqual(compose(inverse([3,2,0]),p),[-3,-2,0])
if __name__=='__main__':unittest.main()
