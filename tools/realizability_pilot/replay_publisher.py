#!/usr/bin/python3
"""Publish one recorded mapper input stream into a live Karto replay.

The publisher is deliberately dumb: it reads the JSONL produced during the
recording episode and re-emits the messages in order with a fixed period.  It
never inspects or adapts to the mapper's state.
"""

import argparse
import json
import time

import rospy
from nav2d_msgs.msg import LocalizedScan
from sensor_msgs.msg import LaserScan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    parser.add_argument('--topic', default='/karto_in')
    parser.add_argument('--robot-id', type=int, default=2,
                        help='id the replay impersonates; it must differ from '
                             'the replay mapper own id or the mapper ignores it')
    args = parser.parse_args(rospy.myargv()[1:])

    with open(args.input) as stream:
        records = [json.loads(line) for line in stream if line.strip()]

    rospy.init_node('replay_publisher', anonymous=False)
    publisher = rospy.Publisher(args.topic, LocalizedScan, queue_size=500)
    # Give the mapper time to subscribe before the stream starts.
    deadline = time.time() + 20.0
    while time.time() < deadline and publisher.get_num_connections() == 0:
        rospy.sleep(0.1)

    period = 1.0 / max(args.rate_hz, 0.1)
    for index, record in enumerate(records):
        message = LocalizedScan()
        message.robot_id = int(args.robot_id)
        message.laser_type = int(record.get('laser_type', 0))
        message.x = float(record['x'])
        message.y = float(record['y'])
        message.yaw = float(record['yaw'])
        scan = LaserScan()
        scan.header.frame_id = record.get('frame_id', 'laser')
        scan.header.stamp = rospy.Time.from_sec(float(record['stamp']))
        scan.angle_min = float(record['angle_min'])
        scan.angle_max = float(record['angle_max'])
        scan.angle_increment = float(record['angle_increment'])
        scan.range_min = float(record['range_min'])
        scan.range_max = float(record['range_max'])
        scan.ranges = [float(value) for value in record['ranges']]
        scan.intensities = []
        message.scan = scan
        publisher.publish(message)
        if index % 10 == 0:
            rospy.loginfo('replay_publisher: %d/%d', index + 1, len(records))
        time.sleep(period)
    # Let the mapper drain the queue before the harness asks for the dump.
    rospy.sleep(1.5)
    print(json.dumps({'published': len(records)}))


if __name__ == '__main__':
    main()
