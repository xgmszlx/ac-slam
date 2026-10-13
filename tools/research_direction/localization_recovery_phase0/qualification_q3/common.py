"""Q3-only files, isolated environment, one-attempt reservation and owned cleanup."""
import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parents[4]
ASSETS=Path('/home/wcqw/ac-slam')
OLD=ROOT/'results/research_direction/localization_recovery_phase0'
OUT=OLD/'qualification_Q3'
HERE=Path(__file__).resolve().parent
EPISODE='NORMAL_GEOMETRY_Q3_QUALIFICATION'
PORT=11481
WORLD=ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.world'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def create(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def atomic(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n');temporary.replace(path)


def environment():
    raw=subprocess.check_output(['bash','-c','source /home/wcqw/ac-slam/catkin_ws/activate.sh && env -0'])
    env={k.decode():v.decode() for k,v in (r.split(b'=',1) for r in raw.split(b'\0') if b'=' in r)}
    overlay=ASSETS/'doc79_ws'
    for name,path in [('ROS_PACKAGE_PATH',overlay/'src'),('CMAKE_PREFIX_PATH',overlay/'devel'),
                      ('LD_LIBRARY_PATH',overlay/'devel/lib'),('PYTHONPATH',overlay/'devel/lib/python3/dist-packages')]:
        env[name]=str(path)+':'+env.get(name,'')
    env.update(ROS_HOME=str(OUT/'runtime/ros_home'),ROS_LOG_DIR=str(OUT/'runtime/ros_logs'),
               ROS_MASTER_URI='http://127.0.0.1:%d'%PORT,ROS_HOSTNAME='127.0.0.1',
               PYTHONDONTWRITEBYTECODE='1',AC_SLAM_Q3_EPISODE_ID=EPISODE)
    return env


def launch_text():
    p=ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/param'
    return '''<launch>
 <param name="use_sim_time" value="true"/><param name="use_tf1" value="true"/>
 <rosparam file="%s/ros.yaml"/>
 <node name="Stage" pkg="stage_ros" type="stageros" args="%s" output="screen"><param name="base_watchdog_timeout" value="0"/></node>
 <node name="Operator" pkg="nav2d_operator" type="operator" output="screen"><remap from="scan" to="base_scan"/><rosparam file="%s/operator.yaml"/><rosparam file="%s/costmap.yaml" ns="local_map"/></node>
 <node name="Mapper" pkg="nav2d_karto" type="mapper" output="screen"><remap from="scan" to="base_scan"/><rosparam file="%s/mapper.yaml"/>
  <param name="enable_edge_provenance" value="true"/><param name="edge_provenance_path" value="%s/raw/edge_provenance.jsonl"/>
  <param name="edge_provenance_run_id" value="%s"/><param name="instrumentation_flush_period_s" value="0.0"/><param name="enable_full_pose_graph_observer" value="true"/></node>
 <node name="Navigator" pkg="nav2d_navigator" type="navigator" output="screen"><rosparam file="%s/navigator.yaml"/>
  <param name="exploration_strategy" value="NearestFrontierPlanner"/><param name="save_path_plan_time" value="%s/raw/planning_time.txt"/></node>
 <node name="GetMap" pkg="nav2d_navigator" type="get_map_client"/>
 <param name="robot_description" command="rosrun xacro xacro $(find p2os_urdf)/defs/pioneer3at.xacro"/>
 <node pkg="robot_state_publisher" type="robot_state_publisher" name="robot_state_publisher"><param name="publish_frequency" value="30.0"/><param name="tf_prefix" value=""/></node>
 <node pkg="p2os_urdf" type="p2os_publisher_3at" name="publisher"/>
</launch>'''%(p,WORLD,p,p,p,OUT,EPISODE,p,OUT)


def protect_manifest():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=str(ROOT)).decode().split('\0')
    paths=[ROOT/n for n in names if n and (n.startswith('results/research_direction/localization_recovery_phase0/')
              or n.startswith('tools/research_direction/localization_recovery_phase0/')
              or n=='docs/research_log/81_localization_recovery_feasibility.md')
              and 'qualification_Q3/' not in n and 'qualification_q3/' not in n]
    paths += [OLD/r['path'] for r in read(OLD/'audit/local_only_capture_manifest.json')['files']]
    paths += [OLD/'baseline/NORMAL_GEOMETRY_271001_A2/loaded_mapper_libraries.json']
    paths += [ASSETS/n for n in read(OLD/'audit/protected_input_hashes.json')]
    paths += [Path(n) for n in read(OLD/'audit/environment_source_hashes.json')]
    paths += [ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/launch/exploration.launch', WORLD,
              WORLD.parent/'p3at.inc',WORLD.parent/'hokuyo.inc',WORLD.parent/'floorplan.inc',WORLD.parent/'map3.png']
    return {str(p):sha(p) for p in sorted(set(paths))}


def check_protection():
    expected=read(OUT/'protocol/protected_pre.json')
    changes=[p for p,digest in expected.items() if not Path(p).is_file() or sha(p)!=digest]
    if changes:raise RuntimeError('Protected files changed: '+str(changes))
    return {'checked':len(expected),'all_unchanged':True,'old_budget_unchanged':True,'mismatches':[]}


def reserve():
    """Separate cumulative ledger, old three-attempt ledger NEVER mutated."""
    import fcntl
    with (OUT/'protocol/reservation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (OUT/'protocol/physical_attempt.json').exists():raise RuntimeError('Q3 attempt already reserved: no retry')
        old=read(OLD/'protocol/budget_ledger.json')
        if len(old['attempts'])!=3:raise RuntimeError('Unexpected prior budget')
        create(OUT/'protocol/physical_attempt.json',{'episode_id':EPISODE,'status':'RESERVED',
             'prior_ledger_sha256':sha(OLD/'protocol/budget_ledger.json'),'prior_total':3,
             'cumulative_total':4,'cumulative_baseline':4,'maximum_new_attempts':1,
             'reservation_wall_epoch_s':time.time()})


def port_free():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:sock.bind(('127.0.0.1',PORT));return True
        except OSError:return False


class OwnedProcesses:
    def __init__(self):
        self.roots=[];self.identities={};self.lock=threading.RLock();self.event=threading.Event()
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()

    def remember(self,pid):
        try:
            process=psutil.Process(pid)
            self.identities[pid]=process.create_time()
        except psutil.Error:pass

    def start(self,args,env,path):
        stream=Path(path).open('x')
        try:process=subprocess.Popen(args,env=env,cwd=str(ROOT),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        except BaseException:stream.close();raise
        process.stream=stream
        with self.lock:self.roots.append(process);self.remember(process.pid)
        return process

    def watch(self):
        while not self.event.wait(.1):
            with self.lock:
                for root in self.roots:
                    try:
                        for child in psutil.Process(root.pid).children(recursive=True):self.remember(child.pid)
                    except psutil.Error:pass

    def live(self):
        result=[]
        for pid,born in list(self.identities.items()):
            try:
                p=psutil.Process(pid)
                if p.create_time()==born and p.is_running() and p.status()!=psutil.STATUS_ZOMBIE:result.append(p)
            except psutil.Error:pass
        return result

    def close(self):
        for root in reversed(self.roots):
            if root.poll() is None:
                try:root.send_signal(signal.SIGINT);root.wait(8)
                except (ProcessLookupError,subprocess.TimeoutExpired):pass
        with self.lock:
            initial=[p.pid for p in self.live()]
            for p in self.live():
                try:p.terminate()
                except psutil.Error:pass
            _,alive=psutil.wait_procs(self.live(),timeout=3)
            for p in alive:
                try:p.kill()
                except psutil.Error:pass
            psutil.wait_procs(alive,timeout=3)
            for root in self.roots:
                try:root.wait(1)
                except subprocess.TimeoutExpired:pass
                root.stream.close()
            residual=[p.pid for p in self.live()]
        self.event.set();self.thread.join(2)
        return {'owned_pid_count':len(self.identities),'owned_pid_start_times':self.identities,
                'fallback_cleanup_pids':initial,'residual_owned_pids':residual,'master_port_released':port_free(),
                'global_kill_used':False,'all_closed':not residual and port_free()}
