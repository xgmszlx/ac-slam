#!/usr/bin/python3
"""New worktree only. Serial bounded native episodes; no replay/stitching."""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
from xml.sax.saxutils import escape
from protocol import ROOT,ASSETS,OUT,SCENARIOS,create_json,atomic_json,reserve_episode,update_episode,sha,freeze

def environment():
    raw=subprocess.check_output(['bash','-c','source /home/wcqw/ac-slam/catkin_ws/activate.sh && env -0'])
    env={k.decode():v.decode() for k,v in (r.split(b'=',1) for r in raw.split(b'\0') if b'=' in r)}
    overlay=ASSETS/'doc79_ws';env['ROS_PACKAGE_PATH']=str(overlay/'src')+':'+env.get('ROS_PACKAGE_PATH','')
    env['CMAKE_PREFIX_PATH']=str(overlay/'devel')+':'+env.get('CMAKE_PREFIX_PATH','')
    env['LD_LIBRARY_PATH']=str(overlay/'devel/lib')+':'+env.get('LD_LIBRARY_PATH','')
    env['PYTHONPATH']=str(overlay/'devel/lib/python3/dist-packages')+':'+env.get('PYTHONPATH','')
    env['ROS_HOME']=str(OUT/'runtime/ros_home');env['ROS_LOG_DIR']=str(OUT/'runtime/ros_logs')
    env['ROS_MASTER_URI']='http://127.0.0.1:11481';env['ROS_HOSTNAME']='127.0.0.1'
    env['PYTHONDONTWRITEBYTECODE']='1';return env
def call(args,env,timeout=15):
    return subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
def wait(args,env,timeout=50):
    end=time.monotonic()+timeout;last=None
    while time.monotonic()<end:
        try:last=call(args,env,5)
        except subprocess.TimeoutExpired:time.sleep(.2);continue
        if last.returncode==0:return last.stdout
        time.sleep(.3)
    raise RuntimeError('readiness failed '+str(args)+': '+str(None if last is None else last.stdout[-500:]))
def start(args,env,path):
    stream=path.open('x');p=subprocess.Popen(args,env=env,cwd=str(ROOT),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    p.stream=stream;return p
def stop(p):
    if p is None:return
    if p.poll() is None:
        os.killpg(p.pid,signal.SIGINT)
        try:p.wait(8)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(4)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    p.stream.close()
def create_world(row,directory):
    inc=ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3'
    startpose=row['start'];common='include "'+str(inc/'p3at.inc')+'"\ninterval_sim 100\nresolution 0.025\nthreads 2\n'
    if SCENARIOS[row['scenario']]['map']=='map3':
        text=common+'include "'+str(inc/'floorplan.inc')+'"\nfloorplan (bitmap "'+str(inc/'map3.png')+'" size [74 74 1] pose [0 0 0 0])\n'
    else:
        text=common+'define wall model ( color "gray30" obstacle_return 1 laser_return 1 )\n'
        text+='wall (size [100 0.3 1] pose [0 1.7 0 0])\nwall (size [100 0.3 1] pose [0 -1.7 0 0])\n'
        text+='wall (size [0.3 3.7 1] pose [-50 0 0 0])\nwall (size [0.3 3.7 1] pose [50 0 0 0])\n'
    text+='pioneer3at (name "robot" pose [%0.12f %0.12f 0 %0.12f])\n'%(startpose[0],startpose[1],startpose[2]*180/3.141592653589793)
    path=directory/'physical.world';path.write_text(text);return path
def create_launch(row,directory):
    config=ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/param';world=OUT/'protocol/worlds'/(row['episode_id']+'.world')
    def x(value):return escape(str(value),{'"':'&quot;'})
    text='''<launch>
 <param name="use_sim_time" value="true"/><param name="use_tf1" value="true"/>
 <rosparam file="%s"/>
 <node name="Stage" pkg="stage_ros" type="stageros" args="-u %s" output="screen"><param name="base_watchdog_timeout" value="0"/></node>
 <node name="Operator" pkg="nav2d_operator" type="operator"><remap from="scan" to="base_scan"/><rosparam file="%s"/><rosparam file="%s" ns="local_map"/></node>
 <node name="Mapper" pkg="nav2d_karto" type="mapper" output="screen"><remap from="scan" to="base_scan"/><rosparam file="%s"/>
   <param name="enable_edge_provenance" value="true"/><param name="edge_provenance_path" value="%s"/><param name="edge_provenance_run_id" value="%s"/>
   <param name="instrumentation_flush_period_s" value="0.0"/><param name="enable_full_pose_graph_observer" value="true"/></node>
 <node name="Navigator" pkg="nav2d_navigator" type="navigator" output="screen"><rosparam file="%s"/><param name="exploration_strategy" value="NearestFrontierPlanner"/><param name="save_path_plan_time" value="%s"/></node>
 <node name="GetMap" pkg="nav2d_navigator" type="get_map_client"/>
 <param name="robot_description" command="rosrun xacro xacro $(find p2os_urdf)/defs/pioneer3at.xacro"/>
 <node pkg="robot_state_publisher" type="robot_state_publisher" name="robot_state_publisher"/>
 <node pkg="p2os_urdf" type="p2os_publisher_3at" name="publisher"/>
</launch>'''%tuple(x(v) for v in [config/'ros.yaml',world,config/'operator.yaml',config/'costmap.yaml',config/'mapper.yaml',
                 directory/'edge_provenance.jsonl',row['episode_id'],config/'navigator.yaml',directory/'planning_time.txt'])
    path=directory/'native.launch';path.write_text(text);return path
def verify_frozen():
    p=json.loads((OUT/'protocol/preregistration.json').read_text())
    for name,digest in p['frozen_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('frozen implementation changed: '+name)
    for name,digest in json.loads((OUT/'audit/environment_source_hashes.json').read_text()).items():
        if sha(name)!=digest:raise RuntimeError('runtime dependency changed '+name)
    for name,digest in json.loads((OUT/'protocol/world_hashes.json').read_text()).items():
        if sha(OUT/name)!=digest:raise RuntimeError('world changed '+name)
def execute(row):
    verify_frozen();directory=reserve_episode(row['episode_id'],'baseline',row);env=environment();children=[]
    spec={**row,'record_stream':True,'sync_export':True,'edge_provenance_path':str(directory/'edge_provenance.jsonl'),'provenance_run_id':row['episode_id']}
    create_json(directory/'episode_spec.json',spec);atomic_json(directory/'run_state.json',{'status':'STARTING'})
    state='TECHNICAL_FAILURE';detail=None;begin=time.monotonic()
    try:
        if call(['rosparam','list'],env,5).returncode==0:raise RuntimeError('existing master on task port; no takeover')
        master=start(['roscore','-p','11481'],env,directory/'roscore.log');children.append(master);wait(['rosparam','list'],env)
        call(['rosparam','set','/doc81/start_gate','false'],env)
        launch=start(['roslaunch',str(create_launch(row,directory))],env,directory/'roslaunch.log');children.append(launch)
        wait(['rosservice','type','/Mapper/doc79_sync_boundary_export'],env,90)
        wait(['rosservice','type','/StartMapping'],env,90)
        driver=start(['/usr/bin/python3',str(Path(__file__).parent/'driver.py'),'--spec',str(directory/'episode_spec.json'),'--output',str(directory)],env,directory/'driver.log');children.append(driver)
        wait(['rosparam','get','/doc81/recorder_ready'],env,60);time.sleep(3)
        (directory/'bootstrap_clock.txt').write_text(call(['rostopic','echo','-n','1','/clock'],env).stdout)
        mapping=start(['rostopic','echo','-n','1','/GetFirstMap/result'],env,directory/'get_first_map.txt');children.append(mapping);time.sleep(.5)
        response=call(['rosservice','call','/StartMapping','{}'],env,10);(directory/'start_mapping.txt').write_text(response.stdout)
        deadline=time.monotonic()+180
        while mapping.poll() is None:
            if driver.poll() is not None:raise RuntimeError('recorder exited during initialization')
            if launch.poll() is not None:raise RuntimeError('launch exited during initialization')
            if time.monotonic()>deadline:raise RuntimeError('initial mapping timeout')
            time.sleep(.3)
        if 'status: 3' not in (directory/'get_first_map.txt').read_text():raise RuntimeError('GetFirstMap failed')
        (directory/'mapper_params.yaml').write_text(call(['rosparam','get','/Mapper'],env).stdout)
        (directory/'rosnode_list.txt').write_text(call(['rosnode','list'],env).stdout)
        # Actual mapped library paths, not merely package resolution.
        paths={}
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
                if 'nav2d_karto/mapper' in cmd and '__name:=Mapper' in cmd:
                    paths[proc.name]={'cmdline':cmd,'maps':(proc/'maps').read_text()}
            except (OSError,UnicodeError):pass
        create_json(directory/'loaded_mapper_libraries.json',paths)
        call(['rosparam','set','/doc81/start_gate','true'],env)
        atomic_json(directory/'run_state.json',{'status':'TASK_RUNNING'})
        with (directory/'process_monitor.csv').open('x') as f:
            f.write('wall_elapsed_s,launch_alive,driver_alive\n')
            while driver.poll() is None:
                elapsed=time.monotonic()-begin;f.write('%.3f,%s,%s\n'%(elapsed,launch.poll() is None,driver.poll() is None));f.flush()
                if launch.poll() is not None:raise RuntimeError('launch exited during task')
                if elapsed>600:raise RuntimeError('frozen episode hard timeout')
                time.sleep(1)
        if driver.returncode:raise RuntimeError('driver exit '+str(driver.returncode))
        result=json.loads((directory/'episode_result.json').read_text());state=result['status'];detail=result.get('reason')
    except BaseException as exc:
        state='INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'TECHNICAL_FAILURE';detail=str(exc)
    finally:
        for child in reversed(children):stop(child)
        atomic_json(directory/'run_state.json',{'status':state,'reason':detail,'wall_duration_s':time.monotonic()-begin})
        update_episode(row['episode_id'],state,detail)
    return state
def prepare():
    # All code and assets must exist before the registration is frozen.
    OUT.mkdir(parents=True,exist_ok=True);worlddir=OUT/'protocol/worlds';worlddir.mkdir(parents=True,exist_ok=True)
    for name in ('ros_home','ros_logs'):(OUT/'runtime'/name).mkdir(parents=True,exist_ok=True)
    from protocol import SEEDS,seeded_start
    hashes={}
    for s in SCENARIOS:
        for seed in SEEDS:
            row={'episode_id':s+'_'+str(seed),'scenario':s,'start':seeded_start(s,seed)}
            path=create_world(row,worlddir);target=worlddir/(row['episode_id']+'.world')
            path.rename(target);hashes[str(target.relative_to(OUT))]=sha(target)
    create_json(OUT/'protocol/world_hashes.json',hashes)
    paths=[ASSETS/'doc79_ws/devel/lib/nav2d_karto/mapper',ASSETS/'doc79_ws/devel/lib/libMultiMapper.so',ASSETS/'doc79_ws/devel/lib/libOpenKarto.so']
    paths += [ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/param'/n for n in ('mapper.yaml','ros.yaml','operator.yaml','costmap.yaml','navigator.yaml')]
    paths += [ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3'/n for n in ('p3at.inc','hokuyo.inc','floorplan.inc','map3.png')]
    paths += [ROOT/'tools/realizability_pilot/doc79_sync_validation/driver.py']
    create_json(OUT/'audit/environment_source_hashes.json',{str(p):sha(p) for p in paths})
    freeze()
def run(max_episodes=9):
    from analysis import analyze_episode,freeze_healthy,analyze_suite
    matrix=json.loads((OUT/'protocol/frozen_baseline_matrix.json').read_text());used=0
    ledger=json.loads((OUT/'protocol/budget_ledger.json').read_text())
    completed={r['episode_id']:r['status'] for r in ledger['attempts']}
    if any(v not in ('SUCCEEDED','NAVIGATION_FAILED') for v in completed.values()):raise RuntimeError('previous failed/interrupted attempt: explicit technical amendment required')
    for row in matrix:
        if row['episode_id'] in completed:continue
        if used>=max_episodes:break
        if row['scenario']!='NORMAL_GEOMETRY' and not (OUT/'protocol/healthy_threshold.json').exists():freeze_healthy()
        print('START '+row['episode_id'],flush=True);status=execute(row);used+=1
        print('END '+row['episode_id']+' '+status,flush=True)
        if status=='TECHNICAL_FAILURE' or status=='INTERRUPTED':break
        metric=analyze_episode(OUT/'baseline'/row['episode_id'])
        if not metric['technical_valid']:print('MEASUREMENT_FAIL: '+str(metric['technical_reasons']),flush=True);break
    analyze_suite()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','analyze']);p.add_argument('--max-episodes',type=int,default=9);a=p.parse_args()
    if a.command=='prepare':prepare()
    elif a.command=='run':run(a.max_episodes)
    else:
        from analysis import analyze_suite
        analyze_suite()
