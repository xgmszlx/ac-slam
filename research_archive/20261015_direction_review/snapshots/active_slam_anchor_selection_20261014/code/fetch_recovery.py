import requests,json,re,pathlib,urllib.parse,concurrent.futures
root=pathlib.Path('/home/wcqw/active_slam_anchor_selection_20261014')
sha='64a0e9ec968e98747a8c2cd53966c2fce4c8c449'
paths=['CNN','Dataset Generator','SLAM-Recovery','merger']
def tree(p):
 u='https://github.com/ans-qureshi/SLAM-Recovery/tree/'+sha+'/'+urllib.parse.quote(p)
 r=requests.get(u,timeout=25)
 (root/'sources'/('tree_'+p.replace(' ','_').replace('/','_')+'.html')).write_text(r.text)
 for t in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',r.text,re.S):
  try:
   j=json.loads(t)
   if 'payload' in j:return j['payload']['codeViewRepoRoute']['tree']['items']
  except Exception:pass
 return [{'path':p,'error':r.status_code}]
items=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 for rows in ex.map(tree,paths):items+=rows
(root/'audit/recovery_tree.json').write_text(json.dumps(items,indent=2))
print(json.dumps(items,indent=2))
files=[x['path'] for x in items if x.get('contentType')=='file' and x['path'].endswith(('.py','.md','.cpp','.txt','.json','.sh','.xml'))]+['README.md','MINOS-SLAM.sh']
def fetch(p):
 r=requests.get('https://raw.githubusercontent.com/ans-qureshi/SLAM-Recovery/'+sha+'/'+urllib.parse.quote(p),timeout=25)
 out=root/'sources/recovery'/p;out.parent.mkdir(parents=True,exist_ok=True)
 if r.status_code==200 and len(r.content)<1000000:out.write_bytes(r.content)
 return {'path':p,'status':r.status_code,'bytes':len(r.content)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:result=list(ex.map(fetch,files))
(root/'audit/recovery_fetch.json').write_text(json.dumps(result,indent=2));print(result)
