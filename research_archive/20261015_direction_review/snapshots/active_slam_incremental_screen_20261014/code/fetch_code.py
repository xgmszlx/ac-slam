import requests,pathlib,json,urllib.parse,concurrent.futures
R=pathlib.Path(__file__).resolve().parents[1];repos={x['name']:x for x in json.loads((R/'audit/repositories.json').read_text())}
jobs=[('mapex','scripts/explore.py'),('mapex','scripts/sim_utils.py'),('mapex','scripts/lama_pred_utils.py'),('mapex','scripts/calc_metrics_subdirectory.py'),('mapex','configs/base.yaml'),('mapex','.gitmodules'),('graph','src/'),('graph','package.xml'),('graph','CMakeLists.txt'),('helpme','start.sh'),('helpme','merger_node.cpp'),('activesplat','environment.yaml'),('activesplat','requirements.txt'),('activesplat','launch/habitat.launch'),('metricsemantic','.gitmodules')]
jobs=[x for x in jobs if not x[1].endswith('/')]
def f(x):
 name,p=x;q=repos[name];u='https://raw.githubusercontent.com/'+q['repo']+'/'+q['sha']+'/'+urllib.parse.quote(p)
 try:
  s=requests.get(u,timeout=25);data=s.content
  if s.status_code==200 and len(data)<1000000:
   dst=R/'sources'/name/p;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
  return {'name':name,'path':p,'status':s.status_code,'bytes':len(data)}
 except Exception as e:return {'name':name,'path':p,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rs=list(ex.map(f,jobs))
(R/'audit/source_fetch.json').write_text(json.dumps(rs,indent=2));print(json.dumps(rs,indent=2))
