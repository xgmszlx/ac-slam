import requests,pathlib,json,re,urllib.parse,concurrent.futures
root=pathlib.Path('/home/wcqw/active_slam_anchor_selection_20261014'); rec='ans-qureshi/SLAM-Recovery';um='Seba-san/UncertaintyMap';rs='64a0e9ec968e98747a8c2cd53966c2fce4c8c449';us='7e5007307dc9525e3474cb6aaf1ac5ae65def811'
jobs=[(rec,rs,'merger/src'),(um,us,'kf_slam'),(um,us,'data')]
def tree(x):
 repo,sha,p=x;r=requests.get('https://github.com/'+repo+'/tree/'+sha+'/'+urllib.parse.quote(p),timeout=25)
 (root/'sources'/('tree_'+repo.split('/')[-1]+'_'+p.replace('/','_')+'.html')).write_text(r.text)
 for t in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',r.text,re.S):
  try:return {'repo':repo,'sha':sha,'items':json.loads(t)['payload']['codeViewTreeRoute']['tree']['items']}
  except Exception:pass
 return {'repo':repo,'sha':sha,'status':r.status_code,'items':[]}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:trees=list(ex.map(tree,jobs))
(root/'audit/extra_trees.json').write_text(json.dumps(trees,indent=2));print(json.dumps(trees,indent=2))
paths=[(rec,rs,'CNN/Training.ipynb'),(rec,rs,'Dataset Generator/DataOrganizer.ipynb')]
for t in trees:
 for i in t['items']:
  p=i['path']
  if p.endswith('.cpp') or p.split('/')[-1] in ['KF.py','test.launch','run.sh','requirements.txt','parameters.yaml','master_simulations.py','prepare_simulation.py','way_point_manager.py','simulaciones_planificadas.yaml','uncertainty_frointier.py','map_server.py','active_slam_core_rrt.py','simulated_2d_slam2.py','rrt_planning.py']:
   paths.append((t['repo'],t['sha'],p))
def fetch(x):
 repo,sha,p=x;u='https://raw.githubusercontent.com/'+repo+'/'+sha+'/'+urllib.parse.quote(p)
 r=requests.get(u,timeout=25,stream=True);data=bytearray()
 for b in r.iter_content(16384):
  data.extend(b)
  if len(data)>1000000:r.close();return dict(repo=repo,path=p,status=r.status_code,oversize=True)
 if r.status_code==200:
  out=root/'sources'/('recovery' if repo==rec else 'uncertainty')/p;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
 return dict(repo=repo,path=p,status=r.status_code,bytes=len(data))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:res=list(ex.map(fetch,paths))
(root/'audit/extra_fetch.json').write_text(json.dumps(res,indent=2));print(res)
