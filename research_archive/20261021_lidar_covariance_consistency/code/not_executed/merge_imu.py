import rosbag, sys
SRC=sys.argv[1]; DST=sys.argv[2]
ACC="/d400/accel/sample"; GYR="/d400/gyro/sample"; OUT="/d400/imu0"
msgs=[]
with rosbag.Bag(SRC,'r') as b:
    for topic,msg,t in b.read_messages(topics=[ACC,GYR]):
        kind = 0 if topic==ACC else 1
        msgs.append((msg.header.stamp.to_sec(), kind, msg))
msgs.sort(key=lambda x:x[0])
print(f"accel/gyro 共 {len(msgs)} 条")
with rosbag.Bag(DST,'w') as out:
    prev=None
    n=0
    for ts,kind,msg in msgs:
        if prev is None: prev=msg
        m=type(prev)()
        m.header=msg.header
        if kind==0:
            m.linear_acceleration=msg.linear_acceleration
            if prev is not None and getattr(prev,'linear_acceleration',None) is not None:
                m.angular_velocity=prev.angular_velocity
        else:
            m.angular_velocity=msg.angular_velocity
            m.linear_acceleration=prev.linear_acceleration
        m.orientation_covariance=[-1.0]+[0.0]*8
        for i in range(9): m.angular_velocity_covariance[i]=0.0
        for i in range(9): m.linear_acceleration_covariance[i]=0.0
        out.write(OUT,m,msg.header.stamp)
        prev=msg; n+=1
print(f"写入 {n} 条 -> {OUT}")
