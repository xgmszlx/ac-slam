"""Read-only offline diagnostic samples: every tenth original front scan, fixed by index."""
from pathlib import Path
import rosbag,numpy as np,json
p=Path(__file__).resolve().parents[1]
for seq in ['static_0','lt_changes_0']:
 stamps=[];ranges=[];seqs=[]
 with rosbag.Bag(str(p/'data'/(seq+'.bag')),'r') as b:
  for i,(_,m,t) in enumerate(b.read_messages(topics=['/laser_scan_front/scan'])):
   if i%10:continue
   stamps.append(m.header.stamp.to_nsec());ranges.append(m.ranges);seqs.append(m.header.seq)
 np.savez_compressed(str(p/'results'/(seq+'_scan_samples.npz')),stamp_ns=np.array(stamps,dtype=np.int64),ranges=np.array(ranges,dtype=np.float32),seq=np.array(seqs))
 print(seq,len(stamps))
