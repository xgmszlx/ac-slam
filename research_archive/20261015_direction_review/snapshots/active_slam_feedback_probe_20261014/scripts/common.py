"""Isolated execution, immutable attempts, owned-process cleanup."""
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
PORT = 11491
ASSETS = Path('/home/wcqw/ac-slam/baseline/Graph-Based_SLAM-Aware_Exploration/world')

def clean(x):
    if isinstance(x, float) and not math.isfinite(x): return str(x)
    if isinstance(x, dict): return {k:clean(v) for k,v in x.items()}
    if isinstance(x, (tuple,list)): return [clean(v) for v in x]
    return x

def create(p, x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(clean(x),f,ensure_ascii=False,indent=2,allow_nan=False)

def atomic(p,x):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False));tmp.replace(p)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def environment(run):
    command='source /opt/ros/noetic/setup.bash && source /home/wcqw/active_slam_topic_audit_20261014/frontier_build_ws/devel/setup.bash && env -0'
    raw=subprocess.check_output(['bash','-c',command])
    env={k.decode():v.decode() for k,v in (r.split(b'=',1) for r in raw.split(b'\0') if b'=' in r)}
    env['PYTHONPATH']=env.get('PYTHONPATH','')+':/home/wcqw/ac-slam/catkin_ws/python'
    env.update(ROS_HOME=str(run/'runtime/ros_home'),ROS_LOG_DIR=str(run/'runtime/ros_logs'),
      ROS_MASTER_URI='http://127.0.0.1:%d'%PORT,ROS_HOSTNAME='127.0.0.1',
      PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    return env

def port_free():
    with socket.socket() as s:
        try:s.bind(('127.0.0.1',PORT));return True
        except OSError:return False

def reserve(kind,map_name,block=None,route=None):
    import fcntl
    p=ROOT/'protocol/budget.json'
    with (ROOT/'protocol/budget.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);b=json.loads(p.read_text())
        count=sum(a['kind']==kind for a in b['attempts'])
        if count>=b['maximum_'+kind+'_attempts'] or len(b['attempts'])>=b['maximum_total_attempts']:
            raise RuntimeError('Attempt budget exhausted')
        if psutil.disk_usage(str(ROOT)).free<2*1024**3:raise RuntimeError('Disk guard: less than 2 GiB free')
        name='%s_%02d_%s'%(kind,count+1,map_name)
        run=ROOT/'runs'/name;run.mkdir(exist_ok=False)
        for d in ['raw','results','runtime']: (run/d).mkdir()
        row={'id':name,'kind':kind,'map':map_name,'block':block,'route':route,
             'status':'RESERVED_BEFORE_ANY_ROS_OR_STAGE_START','reserved_wall_s':time.time()}
        b['attempts'].append(row);atomic(p,b);create(run/'attempt.json',row)
        return run

def finish_budget(run,status):
    import fcntl
    p=ROOT/'protocol/budget.json'
    with (ROOT/'protocol/budget.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);b=json.loads(p.read_text())
        for a in b['attempts']:
            if a['id']==run.name:a.update(status=status,finished_wall_s=time.time())
        atomic(p,b)

class Owned:
    def __init__(self):
        self.roots=[];self.identities={};self.lock=threading.RLock();self.done=threading.Event()
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
    def start(self,args,env,log):
        stream=Path(log).open('x');p=subprocess.Popen(args,env=env,cwd=str(ROOT),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        p.stream=stream
        with self.lock:self.roots.append(p);self.remember(p.pid)
        return p
    def remember(self,pid):
        try:self.identities[pid]=psutil.Process(pid).create_time()
        except psutil.Error:pass
    def watch(self):
        while not self.done.wait(.1):
            with self.lock:
                for r in self.roots:
                    try:
                        for p in psutil.Process(r.pid).children(recursive=True):self.remember(p.pid)
                    except psutil.Error:pass
    def live(self):
        out=[]
        for pid,birth in list(self.identities.items()):
            try:
                p=psutil.Process(pid)
                if p.create_time()==birth and p.is_running() and p.status()!=psutil.STATUS_ZOMBIE:out.append(p)
            except psutil.Error:pass
        return out
    def close(self):
        for p in reversed(self.roots):
            if p.poll() is None:
                try:p.send_signal(signal.SIGINT);p.wait(8)
                except (ProcessLookupError,subprocess.TimeoutExpired):pass
        with self.lock:
            remaining=self.live()
            for p in remaining:
                try:p.terminate()
                except psutil.Error:pass
            _,alive=psutil.wait_procs(remaining,timeout=3)
            for p in alive:
                try:p.kill()
                except psutil.Error:pass
            psutil.wait_procs(alive,timeout=3)
        self.done.set();self.thread.join(1)
        for p in self.roots:p.stream.close()
        return {'owned_identities':len(self.identities),'alive_after':[(p.pid,p.name()) for p in self.live()],'port_free':port_free()}
