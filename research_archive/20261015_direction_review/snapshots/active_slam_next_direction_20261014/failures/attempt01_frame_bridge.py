#!/usr/bin/python3
"""Rename Stage's odometry reference only; never subscribe to truth."""
import rospy
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry

def main():
    rospy.init_node('stage_frame_bridge')
    tf_pub=rospy.Publisher('/tf',TFMessage,queue_size=100)
    odom_pub=rospy.Publisher('/wheel/odom',Odometry,queue_size=20)
    def on_tf(msg):
        for t in msg.transforms:
            if t.header.frame_id.lstrip('/')=='odom':t.header.frame_id='wheel_odom'
        tf_pub.publish(msg)
    def on_odom(msg):
        msg.header.frame_id='wheel_odom';msg.child_frame_id='base_footprint'
        odom_pub.publish(msg)
    rospy.Subscriber('/stage_tf',TFMessage,on_tf,queue_size=200)
    rospy.Subscriber('/wheel/odom_native',Odometry,on_odom,queue_size=50)
    rospy.spin()
if __name__=='__main__':main()
