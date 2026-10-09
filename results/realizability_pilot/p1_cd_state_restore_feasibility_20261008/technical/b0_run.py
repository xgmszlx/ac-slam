#!/usr/bin/python3
"""Five-run frozen technical matrix. Each row uses a fresh ROS master/process."""
import argparse
import concurrent.futures
import io
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from b0_tools import OUT, WS, ROOT, SOURCE, base_pose, compose, inverse, read, sha, write

def wait_until(predicate, timeout=40., description='condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise RuntimeError('timeout: ' + description)

def verify_frozen():
    path = OUT / 'protocol/frozen_technical_experiment.json'
    assert sha(path) == read(OUT / 'protocol/frozen_hash.json')['sha256']
    protocol = read(path)
    for relative, expected in protocol['software_config_sha256'].items():
        assert sha(OUT / relative) == expected, relative
    for path, expected in protocol['build'].items():
        assert sha(path) == expected, path
    assert sha(SOURCE) == protocol['input']['source_sha256']
    assert sha(OUT / 'technical/input_H.jsonl') == protocol['H_sha256']
    assert sha(OUT / 'technical/input_C.jsonl') == protocol['C_sha256']
    return protocol

def worker(label):
    import hashlib
    import threading
    import rospy
    import tf2_ros
    from geometry_msgs.msg import TransformStamped
    from sensor_msgs.msg import LaserScan
    from std_srvs.srv import Trigger
    from slam_toolbox_msgs.srv import SerializePoseGraph, DeserializePoseGraph, DeserializePoseGraphRequest

    verify_frozen()
    directory = OUT / 'technical/runs' / label
    rospy.init_node('cd_b0_input', anonymous=False, disable_signals=True)
    rospy.wait_for_service('/slam_toolbox/b0_status', timeout=35.)
    status_service = rospy.ServiceProxy('/slam_toolbox/b0_status', Trigger)
    dump = rospy.ServiceProxy('/slam_toolbox/b0_dump_graph', Trigger)
    pub = rospy.Publisher('/scan', LaserScan, queue_size=100)
    wire = []
    wire_lock = threading.Lock()

    def observed(scan):
        data = io.BytesIO(); scan.serialize(data)
        with wire_lock:
            wire.append({'seq': scan.header.seq, 'stamp': scan.header.stamp.to_sec(),
                         'serialized_sha256': hashlib.sha256(data.getvalue()).hexdigest()})
    subscription = rospy.Subscriber('/scan', LaserScan, observed, queue_size=100)
    tf_pub = tf2_ros.TransformBroadcaster()
    static_pub = tf2_ros.StaticTransformBroadcaster()
    static = TransformStamped()
    static.header.frame_id = 'base_footprint'; static.child_frame_id = 'cd_b0_laser'
    static.header.stamp = rospy.Time.from_sec(10.)
    static.transform.translation.x = 0.2; static.transform.translation.z = -0.2
    static.transform.rotation.w = 1.
    static_pub.sendTransform(static)
    wait_until(lambda: pub.get_num_connections() >= 2, description='mapper and wire subscriber connection')
    H = [json.loads(x) for x in (OUT / 'technical/input_H.jsonl').open() if x.strip()]
    C = [json.loads(x) for x in (OUT / 'technical/input_C.jsonl').open() if x.strip()]
    rows = H + C if label == 'continuous' else H if label == 'checkpoint' else C
    first_index = 20 if label.startswith('restore_') else 0
    # rospy serialization assigns seq from publisher.impl.seq, rather than the
    # user-supplied header. Preserve the frozen global sequence on the wire.
    pub.impl.seq = first_index
    sent = []

    def publish(index, row):
        pose = base_pose(row)
        t = rospy.Time.from_sec(10. + row['stamp'])
        transform = TransformStamped()
        transform.header.stamp = t; transform.header.frame_id = 'odom'
        transform.child_frame_id = 'base_footprint'
        transform.transform.translation.x = pose[0]
        transform.transform.translation.y = pose[1]
        import math
        transform.transform.rotation.z = math.sin(pose[2] / 2.)
        transform.transform.rotation.w = math.cos(pose[2] / 2.)
        tf_pub.sendTransform(transform)
        scan = LaserScan()
        scan.header.stamp = t; scan.header.frame_id = 'cd_b0_laser'
        for key in ('angle_min', 'angle_max', 'angle_increment', 'range_min', 'range_max'):
            setattr(scan, key, row[key])
        scan.ranges = row['ranges']
        pub.publish(scan)
        assert scan.header.seq == index, 'publisher altered frozen global sequence'
        data = io.BytesIO(); scan.serialize(data)
        sent.append({'input_index': index, 'seq': scan.header.seq, 'stamp': t.to_sec(),
                     'serialized_sha256': hashlib.sha256(data.getvalue()).hexdigest()})

    restore_info = None
    start = time.monotonic()
    if label.startswith('restore_'):
        rospy.wait_for_service('/slam_toolbox/deserialize_map', timeout=10.)
        service = rospy.ServiceProxy('/slam_toolbox/deserialize_map', DeserializePoseGraph)
        req = DeserializePoseGraphRequest()
        req.filename = str(OUT / 'technical/runs/checkpoint/checkpoint_H')
        req.match_type = req.START_AT_GIVEN_POSE
        initial = read(OUT / 'technical/checkpoint_manifest.json')['restore_initial_pose']
        req.initial_pose.x, req.initial_pose.y, req.initial_pose.theta = initial
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(service, req)
            wait_until(lambda: pub.get_num_connections() >= 3, description='deserialize metadata subscriber connection')
            publish(first_index, rows[0])
            future.result(timeout=40.)
        restore_info = {'mode': 'START_AT_GIVEN_POSE', 'initial_pose': initial,
                        'metadata_and_first_C_same_publication': True,
                        'checkpoint_posegraph_sha256': sha(req.filename + '.posegraph'),
                        'checkpoint_data_sha256': sha(req.filename + '.data')}
        rest = enumerate(rows[1:], first_index + 1)
    else:
        rest = enumerate(rows, first_index)
    for index, row in rest:
        publish(index, row)
        time.sleep(0.2)  # pacing only, never evidence of a drained queue
    publication_finished = time.monotonic()
    write(directory / 'publisher.json', {'expected': len(rows), 'published': len(sent),
                                         'complete': len(sent) == len(rows), 'messages': sent})

    def drained():
        response = status_service()
        value = json.loads(response.message)
        return value if (value['callbacks'] == len(rows) and value['processed'] == value['accepted']
                         and value['queue_size'] == 0 and not value['in_flight']) else None
    barrier = wait_until(drained, description='exact callback / processed / queue / in-flight barrier')
    wait_until(lambda: len(wire) == len(rows), description='wire recording complete')
    assert wire == [{k: row[k] for k in ('seq', 'stamp', 'serialized_sha256')} for row in sent]
    write(directory / 'wire_input.json', wire)
    rospy.set_param('/slam_toolbox/b0_expected_callbacks', len(rows))
    rospy.set_param('/slam_toolbox/b0_graph_output', str(directory / 'graph.json'))
    response = dump()
    assert response.success, response.message
    write(directory / 'barrier.json', {'publisher_completed': True,
                                      'scan_filter_pending_inferred_zero': barrier['callbacks'] == len(rows),
                                      'snapshot_service_success': response.success,
                                      'snapshot_lock_order': 'queue then mapper mutex; no more input publication',
                                      'observation': barrier,
                                      'drain_wall_s': time.monotonic() - publication_finished})
    if label == 'checkpoint':
        rospy.wait_for_service('/slam_toolbox/serialize_map', timeout=10.)
        filename = str(directory / 'checkpoint_H')
        rospy.ServiceProxy('/slam_toolbox/serialize_map', SerializePoseGraph)(filename)
        assert Path(filename + '.posegraph').stat().st_size > 0
        assert Path(filename + '.data').stat().st_size > 0
        rospy.set_param('/slam_toolbox/b0_graph_output', str(directory / 'graph_after_save.json'))
        response = dump(); assert response.success, response.message
        assert sha(directory / 'graph_after_save.json') == sha(directory / 'graph.json')
        graph = read(directory / 'graph.json')
        last = max(graph['nodes'], key=lambda n: n['id'])
        initial = compose(compose(last['corrected'], inverse(last['odom'])), base_pose(C[0]))
        manifest = {'cut_index': 20, 'H_count': 20, 'C_count': 13,
                    'archive_files': {p: {'sha256': sha(filename + p), 'bytes': Path(filename + p).stat().st_size}
                                      for p in ('.posegraph', '.data')},
                    'graph_before_after_save_exact': True,
                    'graph_sha256': sha(directory / 'graph.json'), 'barrier': barrier,
                    'restore_initial_pose': initial,
                    'initial_pose_rule_inputs': {'last_H_corrected': last['corrected'],
                                                'last_H_odom': last['odom'], 'first_C_base_odom': base_pose(C[0])}}
        write(OUT / 'technical/checkpoint_manifest.json', manifest)
        write(OUT / 'technical/checkpoint_barrier.json', read(directory / 'barrier.json'))
    result = {'completed': True, 'label': label, 'wall_s': time.monotonic() - start,
              'barrier': barrier, 'graph_sha256': sha(directory / 'graph.json'), 'restore': restore_info}
    write(directory / 'status.json', result)
    print(json.dumps(result), flush=True)
    rospy.signal_shutdown('technical input complete')

def terminate_group(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try: process.wait(timeout=12.)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=5.)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()

def matrix():
    protocol = verify_frozen()
    assert (OUT / 'audit/integrity_before.json').is_file()
    ledger = []
    for number, label in enumerate(protocol['run_order']):
        directory = OUT / 'technical/runs' / label
        if directory.exists():
            raise RuntimeError('frozen matrix row already exists; no automatic retries: ' + label)
        directory.mkdir(parents=True)
        port = 17680 + number
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
        env = dict(os.environ, ROS_MASTER_URI='http://localhost:{}/'.format(port),
                   ROS_HOSTNAME='localhost', ROS_HOME=str(directory / 'ros_home'),
                   ROS_LOG_DIR=str(directory / 'ros_home/log'))
        master = mapper = None
        opened = []
        row = {'label': label, 'port': port, 'start_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        try:
            import xmlrpc.client
            log = (directory / 'roscore.log').open('w'); opened.append(log)
            master = subprocess.Popen(['/opt/ros/noetic/bin/roscore', '-p', str(port)],
                                      env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            def ready():
                if master.poll() is not None: raise RuntimeError('roscore exited')
                try: return xmlrpc.client.ServerProxy(env['ROS_MASTER_URI']).getUri('/cd_b0')[0] == 1
                except (OSError, xmlrpc.client.Error): return False
            wait_until(ready, timeout=25., description='fresh ROS master')
            import yaml
            config = yaml.safe_load((OUT / 'technical/parameters.yaml').read_text())
            # rosparam loads into this isolated master, never the production master.
            import rosgraph
            rosgraph.Master('/cd_b0', master_uri=env['ROS_MASTER_URI']).setParam('/slam_toolbox', config)
            log = (directory / 'mapper.log').open('w'); opened.append(log)
            mapper = subprocess.Popen([str(WS / 'devel/lib/slam_toolbox/sync_slam_toolbox_node'), '__name:=slam_toolbox'],
                                      env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            # Actual process mappings identify which similarly named libraries loaded.
            wait_until(lambda: (Path('/proc') / str(mapper.pid) / 'maps').exists(), timeout=5.)
            time.sleep(0.5)  # library startup only, not the checkpoint drain gate
            maps = (Path('/proc') / str(mapper.pid) / 'maps').read_text()
            libraries = sorted({line.split()[-1] for line in maps.splitlines() if '.so' in line and line.split()[-1].startswith('/')})
            write(directory / 'loaded_libraries.json', {p: sha(p) for p in libraries if Path(p).is_file()})
            log = (directory / 'worker.log').open('w'); opened.append(log)
            worker_process = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).resolve()), '--worker', label],
                                               env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try: code = worker_process.wait(timeout=protocol['per_run_timeout_s'])
            except subprocess.TimeoutExpired:
                terminate_group(worker_process)
                raise RuntimeError('frozen per-run hard timeout')
            if code != 0: raise RuntimeError('worker exit {}'.format(code))
            if mapper.poll() is not None: raise RuntimeError('mapper exited {}'.format(mapper.returncode))
            row['completed'] = True
        except Exception as e:
            row.update(completed=False, error=str(e))
            write(directory / 'status.json', row)
        finally:
            terminate_group(mapper); terminate_group(master)
            for f in opened: f.close()
        row['end_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        ledger.append(row); write(OUT / 'technical/run_ledger.json', ledger)
        print(json.dumps(row), flush=True)
        if not row['completed']:
            raise SystemExit('frozen matrix stopped; failed row is retained without retry')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=['continuous', 'checkpoint', 'restore_1', 'restore_2', 'restore_3'])
    args = parser.parse_args()
    worker(args.worker) if args.worker else matrix()

if __name__ == '__main__':
    main()
