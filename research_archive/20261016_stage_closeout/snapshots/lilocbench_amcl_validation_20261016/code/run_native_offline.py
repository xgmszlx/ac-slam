#!/usr/bin/python3
"""Official AMCL --run-from-bag. Header-time state propagation, wall clock administration."""
from pathlib import Path
import sys,json,os,subprocess,time,signal,socket,xmlrpc.client
p=Path(__file__).resolve().parents[1];key=sys.argv[1];protocol=json.loads((p/'protocol/native_offline_amendment02.json').read_text());spec=next(x for x in protocol['runs'] if x['id']==key)
out=p/'results'/key;out.mkdir(exist_ok=False);env=dict(os.environ);env.update(ROS_MASTER_URI='http://localhost:11331',ROS_HOME=str(out/'ros_home'),ROS_LOG_DIR=str(out/'ros_logs'),ROS_PACKAGE_PATH='/opt/ros/noetic/share',CMAKE_PREFIX_PATH='/opt/ros/noetic',AMCL_AUDIT_SCAN_TOPIC='/base_scan')
if spec['seed'] is not None:env['AMCL_EXPERIMENT_SEED']=str(spec['seed'])
if spec['binary']=='diagnostic':env['LD_LIBRARY_PATH']=str(p/'diagnostic_ws/devel/lib')+':'+env.get('LD_LIBRARY_PATH','')
params=dict(protocol['common_params']);params.update(protocol['initial_params'][spec['sequence']]);params.update(laser_model_type=spec['model'],do_beamskip=spec['skip'])
exe='/opt/ros/noetic/lib/amcl/amcl' if spec['binary']=='installed' else str(p/'diagnostic_ws/devel/lib/amcl/amcl')
commands=[];procs=[];files=[];status={'id':key,'spec':spec,'start_wall':time.time(),'status':'RUNNING','commands':commands,'interface':'official --run-from-bag; /use_sim_time=false; original scan/TF stamps drive propagation; no asynchronous bag player'}
def start(args,name,resource=False):
 commands.append({'command':args,'log':name});f=(out/name).open('w');files.append(f)
 if resource:args=['/usr/bin/time','-v','-o',str(out/'amcl_resource.txt')]+args
 proc=subprocess.Popen(args,cwd=str(out),env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);procs.append(proc);return proc
def wait_for(test,timeout,label):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if test():return
  time.sleep(.1)
 raise RuntimeError('timeout waiting '+label)
def master_ready():
 try:return xmlrpc.client.ServerProxy(env['ROS_MASTER_URI']).getUri('/qualification_check')[0]==1
 except Exception:return False
def map_ready():
 try:return any(a=='/static_map' for a,b in xmlrpc.client.ServerProxy(env['ROS_MASTER_URI']).getSystemState('/qualification_check')[2][2])
 except Exception:return False
try:
 with socket.socket() as s:
  if s.connect_ex(('127.0.0.1',11331))==0:raise RuntimeError('Dedicated ROS port in use')
 core=start(['/opt/ros/noetic/bin/roscore','-p','11331'],'roscore.log');wait_for(master_ready,20,'master')
 server=xmlrpc.client.ServerProxy(env['ROS_MASTER_URI']);server.setParam('/qualification_check','/use_sim_time',False);server.setParam('/qualification_check','/amcl',params)
 (out/'parameters.json').write_text(json.dumps(params,indent=2))
 m=start(['/opt/ros/noetic/lib/map_server/map_server',str(p/'data/map/map_office.yaml'),'__name:=map_server'],'map_server.log');wait_for(map_ready,15,'static map service')
 obs=start(['/usr/bin/python3',str(p/'code/collect_amcl.py'),str(out)],'collector.log');wait_for(lambda:(out/'collector_ready.json').exists(),15,'observer')
 main=start([exe,'--run-from-bag',str(p/'data'/(spec['sequence']+'_native_topics02.bag')),'__name:=amcl'],'launch.log',True)
 deadline=time.monotonic()+180
 while main.poll() is None:
  if obs.poll() is not None or m.poll() is not None:raise RuntimeError('Observer/map server exited')
  if time.monotonic()>deadline:raise TimeoutError('native offline hard timeout 180s')
  time.sleep(.2)
 if main.returncode!=0:raise RuntimeError('AMCL exit '+str(main.returncode))
 time.sleep(2.)
 (out/'parameters_after.json').write_text(json.dumps(server.getParam('/qualification_check','/amcl')[2],indent=2));status.update(status='COMPLETE',estimator_exit=main.returncode)
except Exception as e:status.update(status='FAILED',error=repr(e))
finally:
 for pr in reversed(procs):
  if pr.poll() is None:
   try:os.killpg(pr.pid,signal.SIGINT)
   except ProcessLookupError:pass
   try:pr.wait(timeout=8)
   except subprocess.TimeoutExpired:
    os.killpg(pr.pid,signal.SIGTERM)
    try:pr.wait(timeout=3)
    except subprocess.TimeoutExpired:os.killpg(pr.pid,signal.SIGKILL);pr.wait()
 for f in files:f.close()
 status.update(end_wall=time.time(),elapsed_wall_s=time.time()-status['start_wall'],process_exit=[pr.returncode for pr in procs],clean_collector=(out/'collector_summary.json').exists())
 (out/'run.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
 with (p/'protocol/attempts.jsonl').open('a') as f:f.write(json.dumps(status)+'\n')
 sys.exit(0 if status['status']=='COMPLETE' and status['clean_collector'] else 2)
