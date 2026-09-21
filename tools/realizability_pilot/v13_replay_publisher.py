#!/usr/bin/python3
"""Strict v13 replay publisher with an explicit subscriber-connect gate."""

import argparse
import json
import time
from pathlib import Path

import rospy
from nav2d_msgs.msg import LocalizedScan
from sensor_msgs.msg import LaserScan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    parser.add_argument('--topic', default='/karto_in')
    parser.add_argument('--robot-id', type=int, default=2)
    parser.add_argument('--connect-timeout-s', type=float, default=20.0)
    parser.add_argument('--status-out', required=True)
    args = parser.parse_args(rospy.myargv()[1:])

    with open(args.input) as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    rospy.init_node('v13_replay_publisher', anonymous=False)
    publisher = rospy.Publisher(args.topic, LocalizedScan, queue_size=500)
    deadline = time.time() + args.connect_timeout_s
    while not rospy.is_shutdown() and time.time() < deadline:
        if publisher.get_num_connections() > 0:
            break
        rospy.sleep(0.05)
    connections = publisher.get_num_connections()
    if connections <= 0:
        payload = {'connection_confirmed': False, 'published': 0,
                   'expected': len(records), 'topic': args.topic}
        Path(args.status_out).write_text(json.dumps(payload, sort_keys=True) + '\n')
        raise SystemExit('no subscriber connected to {}'.format(args.topic))

    period = 1.0 / max(args.rate_hz, 0.1)
    published = 0
    for record in records:
        if rospy.is_shutdown():
            break
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
        message.scan = scan
        publisher.publish(message)
        published += 1
        time.sleep(period)
    payload = {'connection_confirmed': connections > 0,
               'connections_at_start': connections,
               'published': published, 'expected': len(records),
               'topic': args.topic}
    Path(args.status_out).write_text(json.dumps(payload, sort_keys=True) + '\n')
    print(json.dumps(payload, sort_keys=True))
    if published != len(records):
        raise SystemExit('publisher stopped before exact stream completion')


if __name__ == '__main__':
    main()
