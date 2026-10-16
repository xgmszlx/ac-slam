"""Topic aliases required by the official native offline AMCL interface. Raw bytes retained."""
from pathlib import Path
import rosbag,json,hashlib,struct
p=Path(__file__).resolve().parents[1];result={}
def update(h,top,msg,t):
 raw=msg[1];h.update(top.encode()+b'\0');h.update(struct.pack('<QQ',t.to_nsec(),len(raw)));h.update(raw)
for seq in ['static_0','lt_changes_0']:
 count={'tf':0,'base_scan':0};h=hashlib.sha256();j=hashlib.sha256();dest=p/'data'/(seq+'_native_topics02.bag')
 assert not dest.exists()
 with rosbag.Bag(str(p/'data'/(seq+'.bag')),'r') as b,rosbag.Bag(str(dest),'w') as o:
  for top,msg,t in b.read_messages(topics=['/tf','/laser_scan_front/scan'],raw=True):
   nt='tf' if top=='/tf' else 'base_scan';o.write(nt,msg,t,raw=True);count[nt]+=1;update(h,nt,msg,t)
 with rosbag.Bag(str(dest),'r') as b:
  for top,msg,t in b.read_messages(raw=True):update(j,top,msg,t)
 assert h.digest()==j.digest()
 result[seq]={'source_topics':['/tf','/laser_scan_front/scan'],'destination_topics':['tf','base_scan'],'framed_payload_topic_order_time_SHA256':h.hexdigest(),'readback_SHA256':j.hexdigest(),'serialized_payload_header_record_time_and_order_identical':True,'messages':count,'bytes':dest.stat().st_size,'bag_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
(p/'audit/native_bag_topic_mapping.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
