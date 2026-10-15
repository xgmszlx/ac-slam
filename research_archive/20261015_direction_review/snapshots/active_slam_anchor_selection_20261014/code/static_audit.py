"""Read-only source/dependency audit; does not import or run author programs."""
import ast,pathlib,json,hashlib,subprocess
R=pathlib.Path(__file__).resolve().parents[1]
rows=[]
for base in [R/'sources/recovery',R/'sources/uncertainty']:
 for p in sorted(base.rglob('*.py')):
  s=p.read_text();entry={'file':str(p.relative_to(R)),'sha256':hashlib.sha256(s.encode()).hexdigest()}
  try:
   t=ast.parse(s,filename=str(p));entry['syntax']='PASS'
   entry['imports']=sorted({(n.module or '').split('.')[0] for n in ast.walk(t) if isinstance(n,ast.ImportFrom)} | {a.name.split('.')[0] for n in ast.walk(t) if isinstance(n,ast.Import) for a in n.names})
  except SyntaxError as e:entry.update(syntax='FAIL',error=str(e))
  rows.append(entry)
(R/'audit/static_sources.json').write_text(json.dumps(rows,indent=2))
# The ROS Python environment is probed without importing neural or simulator modules.
probe="import importlib.util,json,sys;print(json.dumps({'python':sys.version,'modules':{x:importlib.util.find_spec(x) is not None for x in ['numpy','scipy','sklearn','ruamel','matplotlib','rospy','pygame','torch','torchvision','torchsummary','pynput','yaml']}}))"
env=json.loads(subprocess.check_output(['/usr/bin/python3','-c',probe]))
for name,cmd in [('disk',['df','-B1','/']),('memory',['free','-b']),('gpu',['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader']),('ros',['bash','-c','source /opt/ros/noetic/setup.bash && rosversion -d']),('gazebo',['gazebo','--version'])]:
 try:env[name]=subprocess.check_output(cmd,stderr=subprocess.STDOUT).decode()
 except Exception as e:env[name]=str(e)
(R/'audit/environment.json').write_text(json.dumps(env,indent=2))
print(json.dumps({'python_files':len(rows),'syntax_failures':[x for x in rows if x['syntax']=='FAIL'],'environment':env},indent=2))
