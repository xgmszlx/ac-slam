import requests,json,re,pathlib,urllib.parse,concurrent.futures
R=pathlib.Path(__file__).resolve().parents[1];repos={x['name']:x for x in json.loads((R/'audit/repositories.json').read_text())}
jobs=[('mapex','scripts'),('mapex','configs'),('mapex','experiments'),('mapex','pretrained_models'),('fael','fael_planner'),('epic','src'),('metricsemantic','exploration_planner'),('activesplat','src')]
def f(x):
 name,p=x;repo=repos[name];url='https://github.com/'+repo['repo']+'/tree/'+repo['sha']+'/'+urllib.parse.quote(p)
 try:
  res=requests.get(url,timeout=25);(R/'sources'/name/('tree_'+p.replace('/','_')+'.html')).write_text(res.text)
  for t in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',res.text,re.S):
   try:return {'name':name,'path':p,'status':res.status_code,'items':json.loads(t)['payload']['codeViewTreeRoute']['tree']['items']}
   except Exception:pass
  return {'name':name,'path':p,'status':res.status_code,'items':[]}
 except Exception as e:return {'name':name,'path':p,'error':str(e),'items':[]}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:res=list(ex.map(f,jobs))
(R/'audit/trees.json').write_text(json.dumps(res,indent=2));print(json.dumps(res,indent=2))
