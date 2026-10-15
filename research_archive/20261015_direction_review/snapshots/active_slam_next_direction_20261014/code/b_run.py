"""At most two private-master technical starts. Identity-specific cleanup only."""
import os,json,socket,subprocess,time,signal,hashlib
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1];port=11631;p=R/'protocol/b_attempts.json'
budget=json.loads(p.read_text());assert len(budget['attempts'])<2
assert psutil.disk_usage(str(R)).free>2*1024**3
with socket.socket() as s:s.bind(('127.0.0.1',port))
n=len(budget['attempts'])+1;run=R/'results'/('B_technical_%02d'%n);run.mkdir(exist_ok=False)
budget['attempts'].append(dict(id=run.name,status='RESERVED',wall=time.time()));p.write_text(json.dumps(budget,indent=2))
env=os.environ.copy();env.update(ROS_MASTER_URI='http://127.0.0.1:%d'%port,ROS_HOSTNAME='127.0.0.1',ROS_HOME=str(run/'ros_home'),ROS_LOG_DIR=str(run/'ros_logs'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
procs=[];ident={};logs=[];fail=None
def spawn(cmd,label):
 f=(run/(label+'.log')).open('x');logs.append(f);pr=subprocess.Popen(cmd,env=env,cwd=str(R),stdout=f,stderr=subprocess.STDOUT,start_new_session=True);procs.append(pr);ident[pr.pid]=psutil.Process(pr.pid).create_time();return pr
def remember():
 for pr in procs:
  try:
   for c in psutil.Process(pr.pid).children(recursive=True):ident[c.pid]=c.create_time()
  except psutil.Error:pass
try:
 spawn(['roscore','-p',str(port)],'master');time.sleep(2)
 subprocess.check_call(['rosparam','set','/use_sim_time','true'],env=env)
 collector=spawn(['/usr/bin/python3',str(R/'code/b_collect.py'),str(run)],'collector')
 spawn(['/usr/bin/python3',str(R/'code/frame_bridge.py')],'bridge')
 time.sleep(.5);spawn(['roslaunch',str(R/'protocol/b_runtime.launch'),'run:='+str(run)],'launch')
 t=time.monotonic()
 while collector.poll() is None and time.monotonic()-t<80:remember();time.sleep(.2)
 if collector.poll() is None:fail='WALL_TIMEOUT_80S'
 elif collector.returncode:fail='COLLECTOR_EXIT_%d'%collector.returncode
 try:
  params=subprocess.check_output(['rosparam','dump',str(run/'rosparams.yaml')],env=env,timeout=5)
 except Exception as e:(run/'parameter_dump_failure.txt').write_text(str(e))
finally:
 remember()
 for pr in reversed(procs):
  if pr.poll() is None:
   try:os.killpg(pr.pid,signal.SIGINT)
   except ProcessLookupError:pass
 end=time.monotonic()+8
 while time.monotonic()<end and any(pr.poll() is None for pr in procs):time.sleep(.1)
 for pid,birth in ident.items():
  try:
   pr=psutil.Process(pid)
   if pr.create_time()==birth and pr.is_running() and pr.status()!=psutil.STATUS_ZOMBIE:pr.terminate()
  except psutil.Error:pass
 for f in logs:f.close()
 live=[]
 for pid,birth in ident.items():
  try:
   pr=psutil.Process(pid)
   if pr.create_time()==birth and pr.is_running() and pr.status()!=psutil.STATUS_ZOMBIE:live.append(pid)
  except psutil.Error:pass
 (run/'owned_processes.json').write_text(json.dumps(dict(identities=ident,live_after_cleanup=live),indent=2))
 budget=json.loads(p.read_text());budget['attempts'][-1].update(status='COLLECTED_UNQUALIFIED' if not fail else 'FAILED',failure=fail,live_after_cleanup=live);p.write_text(json.dumps(budget,indent=2))
print(json.dumps(dict(run=str(run),failure=fail)))
