#!/usr/bin/python3
"""Publish the bag's initial time once, solely to release ROS startup time waits."""
import rospy,sys
from rosgraph_msgs.msg import Clock
rospy.init_node('bag_clock_bootstrap')
pub=rospy.Publisher('/clock',Clock,queue_size=1,latch=True)
t=int(sys.argv[1]);pub.publish(Clock(rospy.Time(t//10**9,t%10**9)))
rospy.spin()
