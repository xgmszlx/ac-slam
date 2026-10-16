#!/usr/bin/python3
"""One registered run. Fails closed; no automatic retry, no GT online."""
from pathlib import Path
import sys,json,os,subprocess,time,signal,socket,xmlrpc.client,hashlib
p=Path(__file__).resolve().parents[1];key=sys.argv[1];protocol=json.loads((p/'protocol/runs_frozen.json').read_text());spec=next(x for x in protocol['runs']+json.loads((p/'protocol/startup_amendment01.json').read_text())['replacement_runs'] if x['id']==key)
out=p/'results'/key;out.mkdir(exist_ok=False)
env=dict(os.environ);env.update(ROS_MASTER_URI='http://localhost:11331',ROS_HOME=str(out/'ros_home'),ROS_LOG_DIR=str(out/'ros_logs'))
if spec['seed'] is not None:env['AMCL_EXPERIMENT_SEED']=str(spec['seed'])
env['ROS_PACKAGE_PATH']='/opt/ros/noetic/share'
env['CMAKE_PREFIX_PATH']='/opt/ros/noetic'
if spec['binary']=='diagnostic':
 env['ROS_PACKAGE_PATH']=str(p/'diagnostic_ws/src')+':'+env['ROS_PACKAGE_PATH']
 env['CMAKE_PREFIX_PATH']=str(p/'diagnostic_ws/devel')+':'+env['CMAKE_PREFIX_PATH']
 env['LD_LIBRARY_PATH']=str(p/'diagnostic_ws/devel/lib')+':'+env.get('LD_LIBRARY_PATH','')
params=dict(protocol['common_params']);params['laser_model_type']=spec['model'];params['do_beamskip']=spec['skip'];params.update(protocol['initial_params'][spec['sequence']])
launch=['<launch>','<param name="use_sim_time" value="true"/>','<node pkg="map_server" type="map_server" name="map_server" args="'+str(p/'data/map/map_office.yaml')+'" output="screen"/>']
# Installed official node for qualification; source-built diagnostic executable only for registered seed controls.
exe='/opt/ros/noetic/lib/amcl/amcl' if spec['binary']=='installed' else str(p/'diagnostic_ws/devel/lib/amcl/amcl')
launch.append('<node pkg="amcl" type="amcl" name="amcl" output="screen" launch-prefix="/usr/bin/time -v -o '+str(out/'amcl_resource.txt')+'"><remap from="scan" to="/laser_scan_front/scan"/>')
for k,v in params.items():
 typ='bool' if isinstance(v,bool) else ('int' if isinstance(v,int) else ('double' if isinstance(v,float) else 'str'))
 val=str(v).lower() if isinstance(v,bool) else str(v)
 launch.append('<param name="'+k+'" type="'+typ+'" value="'+val+'"/>')
launch+=['</node>','</launch>'];(out/'run.launch').write_text('\n'.join(launch));(out/'parameters.json').write_text(json.dumps(params,indent=2))
commands=[];procs=[];files=[];status={'id':key,'spec':spec,'start_wall':time.time(),'status':'RUNNING','commands':commands}
def start(args,name,resource=False):
 commands.append({'command':args,'log':name})
 f=(out/name).open('w');files.append(f)
 if resource:args=['/usr/bin/time','-v','-o',str(out/'playback_resource.txt')]+args
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
def node_ready():
 try:
  st=xmlrpc.client.ServerProxy(env['ROS_MASTER_URI']).getSystemState('/qualification_check')[2]
  return any(t=='/map' for t,n in st[0]) and any(t=='/amcl_pose' for t,n in st[0]) and any(t=='/laser_scan_front/scan' and '/amcl' in n for t,n in st[1])
 except Exception:return False
try:
 with socket.socket() as s:
  if s.connect_ex(('127.0.0.1',11331))==0:raise RuntimeError('Dedicated ROS port already in use')
 core=start(['/opt/ros/noetic/bin/roscore','-p','11331'],'roscore.log');wait_for(master_ready,20,'master')
 bagmeta=json.loads((p/'audit'/(spec['sequence']+'_bag.json')).read_text())
 clock=start(['/usr/bin/python3',str(p/'code/start_clock.py'),str(int(bagmeta['bag_start']*1e9))],'clock_bootstrap.log')
 launchproc=start(['/opt/ros/noetic/bin/roslaunch','--wait',str(out/'run.launch')],'launch.log');wait_for(node_ready,25,'map and AMCL subscribers')
 obs=start(['/usr/bin/python3',str(p/'code/collect_amcl.py'),str(out)],'collector.log');wait_for(lambda:(out/'collector_ready.json').exists(),15,'observer')
 time.sleep(1.)
 os.killpg(clock.pid,signal.SIGINT);clock.wait(timeout=5)
 play=start(['/opt/ros/noetic/bin/rosbag','play','--clock','--hz','100','--rate',str(protocol['playback_rate']),str(p/'data'/str(spec['sequence']+'.bag')),'--topics','/laser_scan_front/scan','/dingo_velocity_controller/odom','/tf','/tf_static'],'playback.log',True)
 deadline=time.monotonic()+protocol['hard_timeout_wall_s']
 while play.poll() is None:
  if launchproc.poll() is not None or obs.poll() is not None:raise RuntimeError('ROS launch or collector exited during playback')
  if time.monotonic()>deadline:raise TimeoutError('registered wall hard timeout')
  time.sleep(.5)
 if play.returncode!=0:raise RuntimeError('playback exit '+str(play.returncode))
 time.sleep(2.)
 # Snapshot final node parameters before shutdown; no reconfiguration.
 server=xmlrpc.client.ServerProxy(env['ROS_MASTER_URI']);(out/'parameters_after.json').write_text(json.dumps(server.getParam('/qualification_check','/amcl')[2],indent=2))
 status.update(status='COMPLETE',playback_exit=play.returncode)
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
 status.update(end_wall=time.time(),elapsed_wall_s=time.time()-status['start_wall'],process_exit=[pr.returncode for pr in procs])
 status['clean_collector']=(out/'collector_summary.json').exists()
 (out/'run.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
 with (p/'protocol/attempts.jsonl').open('a') as f:f.write(json.dumps(status)+'\n')
 sys.exit(0 if status['status']=='COMPLETE' and status['clean_collector'] else 2)
