#!/usr/bin/python3
"""Rename Stage's odometry reference only; never subscribe to truth."""
import rospy
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry

def main():
    rospy.init_node('stage_frame_bridge')
    tf_pub=rospy.Publisher('/tf',TFMessage,queue_size=100)
    static_pub=rospy.Publisher('/tf_static',TFMessage,queue_size=10,latch=True)
    fixed={}
    odom_pub=rospy.Publisher('/wheel/odom',Odometry,queue_size=20)
    def on_tf(msg):
        dynamic=[]
        for t in msg.transforms:
            if t.header.frame_id.lstrip('/')=='odom':t.header.frame_id='wheel_odom'
            if t.child_frame_id.lstrip('/') in ['base_link','base_laser_link']:
                fixed[t.child_frame_id]=t
            else:dynamic.append(t)
        if fixed:static_pub.publish(TFMessage(list(fixed.values())))
        if dynamic:tf_pub.publish(TFMessage(dynamic))
    def on_odom(msg):
        msg.header.frame_id='wheel_odom';msg.child_frame_id='base_footprint'
        odom_pub.publish(msg)
    rospy.Subscriber('/stage_tf',TFMessage,on_tf,queue_size=200)
    rospy.Subscriber('/wheel/odom_native',Odometry,on_odom,queue_size=50)
    rospy.spin()
if __name__=='__main__':main()
