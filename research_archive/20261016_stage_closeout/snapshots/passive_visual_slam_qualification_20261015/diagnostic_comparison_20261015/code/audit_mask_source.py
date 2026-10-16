import pathlib,json,urllib.request,datetime
N=pathlib.Path(__file__).resolve().parents[1]
headers={'User-Agent':'SLAM-reproduction-audit'}
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as r:return r.read()
try:
 commit=json.loads(get('https://api.github.com/repos/chuanqi305/MobileNet-SSD/commits/master'))['sha']
 tree=json.loads(get('https://api.github.com/repos/chuanqi305/MobileNet-SSD/git/trees/'+commit))['tree']
 target=[a for a in tree if a['path'] in ['deploy.prototxt','mobilenet_iter_73000.caffemodel','demo.py','LICENSE','README.md']]
 result={'commit':commit,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':target,'repository':'https://github.com/chuanqi305/MobileNet-SSD','download_weights_yet':False}
 for f in target:
  if f['path']!='mobilenet_iter_73000.caffemodel':
   b=get('https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/'+commit+'/'+f['path']);d=N/'audit/detector_source';d.mkdir(exist_ok=True);(d/f['path']).write_bytes(b)
 (N/'audit/detector_availability.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
except Exception as e:
 (N/'audit/detector_availability_failure.txt').write_text(repr(e));print(repr(e))
