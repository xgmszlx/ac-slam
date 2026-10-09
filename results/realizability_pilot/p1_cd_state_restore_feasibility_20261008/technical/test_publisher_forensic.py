#!/usr/bin/python3
"""Offline reproduction of actual rospy serialization; no ROS master/backend."""
import io
from types import SimpleNamespace
import unittest
import rospy.topics
from sensor_msgs.msg import LaserScan

class PublisherForensic(unittest.TestCase):
    def publish_to_memory(self, initial_seq):
        packets = []
        sink = SimpleNamespace(write_data=packets.append)
        fake = SimpleNamespace(closed=False, is_latch=False, has_connections=lambda: True,
                               connections=[sink], buff=io.BytesIO(), seq=initial_seq,
                               message_data_sent=0)
        scan = LaserScan(); scan.header.frame_id = 'cd_b0_laser'
        # Execute the installed ROS implementation, rather than mirror it.
        rospy.topics._PublisherImpl.publish(fake, scan)
        decoded = LaserScan().deserialize(packets[0][4:])
        return scan.header.seq, decoded.header.seq

    def test_original_zero_initializer_emits_one(self):
        self.assertEqual(self.publish_to_memory(0), (1, 1))

    def test_original_continuation_initializer_emits_twentyone(self):
        self.assertEqual(self.publish_to_memory(20), (21, 21))

if __name__ == '__main__':
    unittest.main()
