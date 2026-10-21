import sys, numpy as np, rosbag
BAG = sys.argv[1]; OUT = sys.argv[2]
TOPIC = sys.argv[3] if len(sys.argv)>3 else "/laser_scan_front/scan"
ts=[]; ranges=[]
with rosbag.Bag(BAG,'r') as bag:
    info = bag.get_type_and_topic_info().topics
    print("topics:", [ (k,v.message_count) for k,v in info.items() ])
    for topic, msg, t in bag.read_messages(topics=[TOPIC]):
        ts.append(msg.header.stamp.to_sec())
        ranges.append(np.asarray(msg.ranges, dtype=np.float32))
        meta = (msg.angle_min, msg.angle_increment, msg.range_min, msg.range_max)
n = min(len(r) for r in ranges)
R = np.stack([r[:n] for r in ranges])
np.savez_compressed(OUT, ts=np.array(ts), ranges=R, meta=np.array(meta))
print(f"saved {R.shape} -> {OUT}")
print(f"angle_min={meta[0]:.4f} inc={meta[1]:.5f} rmin={meta[2]} rmax={meta[3]}")
print(f"duration {ts[-1]-ts[0]:.1f}s, hz={len(ts)/(ts[-1]-ts[0]):.1f}")
