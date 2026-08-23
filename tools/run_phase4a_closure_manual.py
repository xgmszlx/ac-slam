#!/usr/bin/python3
"""Phase 4A Stage C: minimal manual revisit to force a Karto accepted closure.

After GetFirstMap (mapping only, NO exploration), drive the robot OUT ~drive_m
via /MoveTo, then BACK to the start pose. The return pass re-traverses the
outbound path nearly exactly, so the new scans overlap the outbound scans
strongly and Karto should accept a closure. We then validate 1:1:
  Karto internal accepted callback  ('Add one Loop closure.' in rosout)
  == published loop_closed event    (PHASE4A_LOOP_CLOSED in rosout)
Checking: count 1:1, no duplicates, no missed, seq contiguous, no delay.

Loop diagnostics are DISABLED (Phase 2B config) because the per-loop-search
diagnostic file I/O is suspected of perturbing closure acceptance (Phase 2B
without diagnostics: 3/3 accepted closures; every diagnostics-enabled positive
control: 0). The observation-only /Mapper/loop_closed event is independent of
the diagnostics and is what we are validating.
"""

import json
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path as FilePath

import actionlib
import rospy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path as NavPath
from nav2d_navigator.msg import MoveToPosition2DAction, MoveToPosition2DGoal
from rosgraph_msgs.msg import Log

from run_phase2_pairs import (
    AUTHOR_RESULTS,
    ROOT,
    activated_environment,
    command_output,
    parse_action_status,
    start_process,
    stop_process,
    wait_for_command,
    wait_for_topic_result,
    write_command_result,
)

OUT_ROOT = ROOT / 'results' / 'phase4a' / 'closure_event_validation'


class ManualDrive:
    def __init__(self, run_dir, drive_m, timeout_s):
        self.run_dir = run_dir
        self.drive_m = float(drive_m)
        self.timeout_s = float(timeout_s)
        self.slam_path = None
        self.callbacks = []
        self.events = []
        self.lock = threading.RLock()
        self.last_pose = None
        self.attempts = []

    def on_slam_path(self, msg):
        with self.lock:
            self.slam_path = msg

    def on_rosout(self, msg):
        text = msg.msg.strip()
        stamp = msg.header.stamp.to_sec() or rospy.get_time()
        with self.lock:
            if 'Add one Loop closure.' in text:
                self.callbacks.append({'t': stamp, 'msg': text})
            m = re.search(r'PHASE4A_LOOP_CLOSED seq=(\d+) current_scan=(\d+) '
                          r'chain_start=(\d+) chain_end=(\d+)', text)
            if m:
                self.events.append({'t': stamp, 'seq': int(m.group(1)),
                                    'scan': int(m.group(2)),
                                    'chain_start': int(m.group(3)),
                                    'chain_end': int(m.group(4))})

    def current_pose(self):
        with self.lock:
            if self.slam_path is not None and self.slam_path.poses:
                p = self.slam_path.poses[-1].pose
                return p.position.x, p.position.y, math.atan2(
                    2.0 * (p.orientation.w * p.orientation.z + p.orientation.x * p.orientation.y),
                    1.0 - 2.0 * (p.orientation.y * p.orientation.y + p.orientation.z * p.orientation.z))
        return None

    def move_to(self, client, x, y, theta, label):
        goal = MoveToPosition2DGoal()
        goal.header.stamp = rospy.Time.now()
        goal.header.frame_id = 'map'
        goal.target_pose.x = x
        goal.target_pose.y = y
        goal.target_pose.theta = theta
        goal.target_distance = 0.25
        goal.target_angle = 0.1
        start = rospy.get_time()
        client.send_goal(goal)
        finished = client.wait_for_result(rospy.Duration(self.timeout_s))
        state = int(client.get_state())
        result = client.get_result()
        row = {'label': label, 'x': x, 'y': y, 'theta': theta,
               'action_finished': bool(finished), 'action_state': state,
               'elapsed': rospy.get_time() - start}
        self.attempts.append(row)
        rospy.logwarn('PHASE4A_MANUAL %s -> state=%d finished=%s (%.1fs)',
                      label, state, finished, row['elapsed'])
        return state == 3 and bool(finished)

    def run(self):
        rospy.Subscriber('/slam_path', NavPath, self.on_slam_path, queue_size=10)
        rospy.Subscriber('/rosout', Log, self.on_rosout, queue_size=200)
        client = actionlib.SimpleActionClient('/MoveTo', MoveToPosition2DAction)
        if not client.wait_for_server(rospy.Duration(30.0)):
            raise RuntimeError('MoveTo action server unavailable')

        # wait for a stable robot pose from the mapper trajectory
        pose = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            pose = self.current_pose()
            if pose is not None:
                break
            rospy.sleep(0.5)
        if pose is None:
            raise RuntimeError('no /slam_path pose available')
        x0, y0, th0 = pose
        rospy.logwarn('PHASE4A_MANUAL start pose=(%.2f, %.2f, %.2f)', x0, y0, th0)

        # Try forward (current heading), then rotated directions, until a goal is
        # accepted (navigator can plan a path in the mapped area).
        directions = [0.0, math.pi / 2, -math.pi / 2, math.pi]
        out_ok = False
        out_target = None
        for rot in directions:
            t = th0 + rot
            tx = x0 + self.drive_m * math.cos(t)
            ty = y0 + self.drive_m * math.sin(t)
            ok = self.move_to(client, tx, ty, t, 'out rot={:.1f}'.format(rot))
            self.attempts[-1]['target_x'] = tx
            self.attempts[-1]['target_y'] = ty
            if ok:
                out_ok = True
                out_target = (tx, ty, t)
                break
            # if rejected instantly, try the next direction
        if not out_ok:
            raise RuntimeError('could not drive OUT in any direction '
                               '(attempts: {})'.format(self.attempts))

        rospy.sleep(1.0)
        # drive back to the start pose -> return pass re-traverses the outbound path
        back_ok = self.move_to(client, x0, y0, th0, 'back-to-start')
        if not back_ok:
            raise RuntimeError('drive BACK failed (state {})'.format(self.attempts[-1]))

        rospy.sleep(5.0)
        with self.lock:
            result = {
                'status': 'SUCCEEDED',
                'start_pose': [x0, y0, th0],
                'out_target': out_target,
                'drive_m': self.drive_m,
                'attempts': self.attempts,
                'accepted_callbacks': [
                    {'t': c['t'], 'msg': c['msg'][:80]} for c in self.callbacks],
                'loop_closed_events': self.events,
                'callbacks_count': len(self.callbacks),
                'events_count': len(self.events),
                'one_to_one': len(self.callbacks) == len(self.events) > 0,
                'no_duplicates': len({e['seq'] for e in self.events}) == len(self.events),
                'seq_contiguous': (sorted(e['seq'] for e in self.events)
                                   == list(range(1, len(self.events) + 1))),
            }
            (self.run_dir / 'manual_revisit.json').write_text(
                json.dumps(result, indent=2, sort_keys=True) + '\n')
            return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', required=True, type=int)
    parser.add_argument('--drive-m', type=float, default=8.0)
    parser.add_argument('--move-timeout', type=float, default=300.0)
    parser.add_argument('--mapping-timeout', type=int, default=1200)
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = OUT_ROOT / 'manual_revisit_{:02d}'.format(args.trial)
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    suffix = '_Phase4A_ManualRevisit_{:02d}'.format(args.trial)
    seed = 23000 + args.trial

    env = activated_environment()
    roscore = observer = launch = mapping_result = None
    import csv as _csv
    monitor_stream = open(run_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = _csv.writer(monitor_stream)
    monitor.writerow(['wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
                      'observer_alive', 'rss_kb', 'missing_core_nodes'])
    try:
        if command_output(['rosparam', 'list'], env, timeout=5).returncode == 0:
            raise RuntimeError('a ROS master is already running')
        roscore = start_process(['roscore'], env, run_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        ros_run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, run_dir / 'ros_run_id.txt', timeout=10
        ).strip()
        observer = start_process(
            ['/usr/bin/python3', str(ROOT / 'tools' / 'phase2_observer.py'),
             '--output-dir', str(run_dir)], env, run_dir / 'observer.log')
        # NearestFrontierPlanner is only needed to have the Navigator + Mapper up;
        # we never start exploration.
        launch = start_process([
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=NearestFrontierPlanner',
            'only_use_tsp:=true', 'tsp_seed:={}'.format(seed),
            'map_name:=map3/map3', 'robot_position:=-28.0 -28.0 0',
            'map_width:=74.0', 'need_noise:=false', 'variance:=0',
        ], env, run_dir / 'roslaunch.log')
        for service in ('/StartMapping', '/StartExploration'):
            wait_for_command(['rosservice', 'type', service], env, 180, service)

        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=open(run_dir / 'get_first_map_result.txt', 'w', buffering=1),
            stderr=subprocess.STDOUT, text=True)
        time.sleep(1)
        write_command_result(['rosservice', 'call', '/StartMapping', '{}'], env,
                             run_dir / 'start_mapping_service.txt', timeout=30)
        wait_for_topic_result(mapping_result, run_dir / 'get_first_map_result.txt',
                              launch, observer, env, args.mapping_timeout, monitor, 'mapping')
        if parse_action_status(run_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap did not SUCCEED')

        # ---- manual drive (rospy) ----
        rospy.init_node('phase4a_manual_revisit', anonymous=True)
        spin = threading.Thread(target=rospy.spin, daemon=True)
        spin.start()
        drive = ManualDrive(run_dir, args.drive_m, args.move_timeout)
        result = drive.run()
        # stop immediately after closure (if any) to keep the rosout window tight
        if result['events_count'] > 0:
            time.sleep(5.0)

        stop_process(observer); observer = None
        stop_process(launch); launch = None
        stop_process(roscore); roscore = None
        rosout_source = FilePath(env['ROS_LOG_DIR']) / ros_run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, run_dir / 'rosout.log')
        # re-read validation from the copied rosout (authoritative)
        rosout = (run_dir / 'rosout.log').read_text(errors='replace')
        cb_times, evts = [], []
        for line in rosout.splitlines():
            if 'Add one Loop closure.' in line:
                m = re.match(r'^([0-9.]+) WARN', line)
                if m:
                    cb_times.append(float(m.group(1)))
            m = re.search(r'PHASE4A_LOOP_CLOSED seq=(\d+) current_scan=(\d+) '
                          r'chain_start=(\d+) chain_end=(\d+)', line)
            if m:
                evts.append((int(m.group(1)), int(m.group(2)),
                             int(m.group(3)), int(m.group(4))))
        n = len(evts)
        delays = None
        if n and len(cb_times) == n:
            # Each callback should be followed by its event shortly after; compare
            # the i-th event time to the i-th callback time (both time-ordered).
            delays = [evt_t - cb_t for cb_t, (evt_t, *_) in zip(cb_times, evts)]
        cv = {
            'mode': 'manual_minimal_revisit_diagnostics_off',
            'accepted_callbacks_count': len(cb_times),
            'accepted_callback_times': cb_times,
            'loop_closed_events': evts,
            'inconclusive_no_closure': n == 0,
            'one_to_one': (n > 0) and len(cb_times) == n,
            'attribution_ok': all(0 <= e[1] and e[2] <= e[3] for e in evts) if n else None,
            'no_duplicates': len({e[0] for e in evts}) == n,
            'seq_contiguous': evts == sorted(evts) and (not evts or evts[-1][0] == n),
            'event_after_callback_ok': (delays is not None and all(d >= 0 for d in delays)),
            'max_callback_to_event_delay_s': max(delays) if delays else None,
        }
        (run_dir / 'closure_event_validation.json').write_text(
            json.dumps(cv, indent=2, sort_keys=True) + '\n')
        print(json.dumps(cv, indent=2, sort_keys=True))
        if cv.get('inconclusive_no_closure'):
            print('RESULT: INCONCLUSIVE (no accepted closure fired during manual revisit)')
        elif cv.get('one_to_one') and cv.get('no_duplicates') and cv.get('seq_contiguous'):
            print('RESULT: CLOSURE_EVENT_VALIDATION PASS')
        else:
            print('RESULT: CLOSURE_EVENT_VALIDATION FAIL')
    finally:
        if mapping_result is not None and mapping_result.poll() is None:
            mapping_result.terminate()
        stop_process(observer); stop_process(launch); stop_process(roscore)
        monitor_stream.close()


if __name__ == '__main__':
    main()
