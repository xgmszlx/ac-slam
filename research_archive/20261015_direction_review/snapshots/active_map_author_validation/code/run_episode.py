#!/usr/bin/env python3
"""Bounded owned-process execution; never targets other ROS sessions."""
import argparse,hashlib,json,os,signal,socket,subprocess,time
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1];PORT=11531
ap=argparse.ArgumentParser();ap.add_argument('case',choices=['T0','S0','S1','S2','S3','B1_S1','B1_S3']);args=ap.parse_args();kind='technical' if args.case=='T0' else 'scientific';replay=args.case.startswith('B1_')
with socket.socket() as s:s.bind(('127.0.0.1',PORT))
if psutil.disk_usage(str(R)).free<2*1024**3:raise SystemExit('Disk guard')
p=R/'protocol/attempts.json';b=json.loads(p.read_text());n=sum(x['kind']==kind for x in b['attempts'])
assert n<b['maximum_'+kind+'_attempts']
name=f'{kind}_{n+1:02d}_{args.case}';run=R/'results'/name;run.mkdir(exist_ok=False)
b['attempts'].append(dict(id=name,kind=kind,case=args.case,status='RESERVED_BEFORE_ROS',wall=time.time()));p.write_text(json.dumps(b,indent=2))
frozen=json.loads((R/'protocol/science_frozen.json').read_text());world='old' if kind=='technical' else frozen['cases'][args.case[-2:]]['world'];duration=30 if kind=='technical' else 55 if replay else 50
raw=subprocess.check_output(['bash','-c','source /opt/ros/noetic/setup.bash && source /home/wcqw/active_map_author_validation/catkin_ws/devel/setup.bash && env -0'])
env={k.decode():v.decode() for k,v in (item.split(b'=',1) for item in raw.split(b'\0') if b'=' in item)}
env.update(ROS_MASTER_URI=f'http://127.0.0.1:{PORT}',ROS_HOSTNAME='127.0.0.1',ROS_HOME=str(run/'ros_home'),ROS_LOG_DIR=str(run/'ros_logs'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
env['PYTHONPATH']='/home/wcqw/ac-slam/catkin_ws/python:'+env.get('PYTHONPATH','')
children=[];logs=[];identities={};failure=None
def spawn(cmd,label):
    f=(run/(label+'.log')).open('x');logs.append(f);proc=subprocess.Popen(cmd,env=env,cwd=str(R),stdout=f,stderr=subprocess.STDOUT,start_new_session=True);children.append(proc);identities[proc.pid]=psutil.Process(proc.pid).create_time();return proc
def remember():
    for proc in children:
        try:
            for c in psutil.Process(proc.pid).children(recursive=True):identities[c.pid]=c.create_time()
        except psutil.Error:pass
try:
    spawn(['roscore','-p',str(PORT)],'master');time.sleep(2)
    collector=spawn(['/usr/bin/python3',str(R/'code/ros_episode.py'),str(run),'--case',args.case,'--duration',str(duration)],'collector')
    if replay:
        source=R/'results'/('scientific_02_S1' if args.case=='B1_S1' else 'scientific_04_S3')
        b=json.loads(p.read_text());b['attempts'][-1].update(replay=True,source=str(source));p.write_text(json.dumps(b,indent=2))
        spawn(['roslaunch',str(R/'protocol/passive.launch')],'launch')
        spawn(['/usr/bin/python3',str(R/'code/passive_replay.py'),str(source),str(run)],'player')
    else:spawn(['roslaunch',str(R/'protocol/runtime.launch'),'world_file:='+str(R/'protocol/scenes'/(world+'.world'))],'launch')
    wall=time.monotonic()
    while collector.poll() is None and time.monotonic()-wall<100:
        remember();time.sleep(.2)
    if collector.poll() is None:failure='HARD_WALL_TIMEOUT_100S'
    elif collector.returncode!=0:failure=f'COLLECTOR_EXIT_{collector.returncode}'
except Exception as e:failure=str(e)
finally:
    remember()
    # Stop only process groups created by this runner, then exact tracked descendants.
    for proc in reversed(children):
        if proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGINT)
            except ProcessLookupError:pass
    deadline=time.monotonic()+8
    while time.monotonic()<deadline and any(x.poll() is None for x in children):time.sleep(.1)
    for pid,birth in identities.items():
        try:
            proc=psutil.Process(pid)
            if proc.create_time()==birth and proc.is_running() and proc.status()!=psutil.STATUS_ZOMBIE:proc.terminate()
        except psutil.Error:pass
    for f in logs:f.close()
    live=[]
    for pid,birth in identities.items():
        try:
            proc=psutil.Process(pid)
            if proc.create_time()==birth and proc.is_running() and proc.status()!=psutil.STATUS_ZOMBIE:live.append(pid)
        except psutil.Error:pass
    (run/'owned_processes.json').write_text(json.dumps(dict(identities=identities,live_after_cleanup=live),indent=2))
    if live:failure='OWNED_PROCESSES_REMAIN_'+str(live)
    b=json.loads(p.read_text());b['attempts'][-1].update(status='TECHNICAL_RUN_FAIL' if failure else 'COLLECTED_NOT_YET_QUALIFIED',failure=failure,finished_wall=time.time());p.write_text(json.dumps(b,indent=2))
print(json.dumps(dict(run=str(run),failure=failure)));raise SystemExit(1 if failure else 0)
