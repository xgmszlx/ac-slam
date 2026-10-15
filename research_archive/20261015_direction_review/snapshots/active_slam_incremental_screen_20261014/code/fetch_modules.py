import requests,pathlib,json,re,concurrent.futures,urllib.parse
R=pathlib.Path(__file__).resolve().parents[1];repos={x['name']:x for x in json.loads((R/'audit/repositories.json').read_text())}
trees=[('fael','fael_planner/planner/src'),('epic','src/global_planner/frontier_manager/src'),('metricsemantic','exploration_planner/planner/exploration_manager/src'),('falcon','falcon_planner/exploration_manager/src'),('pipe','eval_deploy')]
repos['pipe']={'repo':'castacks/pipe-planner','sha':'dadde41451c9b42ab5f1fe6cbf2c10a2dcebcfa2'}
def tree(x):
 n,p=x;q=repos[n]
 try:
  s=requests.get('https://github.com/'+q['repo']+'/tree/'+q['sha']+'/'+p,timeout=20);(R/'sources'/n/('tree_'+p.replace('/','_')+'.html')).write_text(s.text)
  for t in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',s.text,re.S):
   try:return dict(name=n,path=p,items=json.loads(t)['payload']['codeViewTreeRoute']['tree']['items'])
   except:pass
  return dict(name=n,path=p,status=s.status_code,items=[])
 except Exception as e:return dict(name=n,path=p,error=str(e),items=[])
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:ts=list(ex.map(tree,trees))
(R/'audit/key_module_trees.json').write_text(json.dumps(ts,indent=2));print(ts)
jobs=[('graph','src/MyPlanner.cpp'),('graph','src/MyPlanner.h'),('activesplat','src/planner/planner.py'),('fael','fael_planner/planner/CMakeLists.txt'),('fael','fael_planner/planner/package.xml')]
for t in ts:
 fs=[x['path'] for x in t['items'] if x.get('contentType')=='file' and x['path'].endswith(('.cpp','.py'))]
 # Representative source paths only, not a whole repository.
 jobs.extend((t['name'],p) for p in fs[:2])
def fetch(x):
 n,p=x;q=repos[n]
 try:
  s=requests.get('https://raw.githubusercontent.com/'+q['repo']+'/'+q['sha']+'/'+urllib.parse.quote(p),timeout=20)
  if s.status_code==200 and len(s.content)<800000:
   out=R/'sources'/n/p;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(s.content)
  return dict(name=n,path=p,status=s.status_code,bytes=len(s.content))
 except Exception as e:return dict(name=n,path=p,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:fs=list(ex.map(fetch,jobs))
(R/'audit/key_module_fetch.json').write_text(json.dumps(fs,indent=2));print(fs)
