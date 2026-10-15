import pathlib,requests,re,json,concurrent.futures,urllib.parse,hashlib
R=pathlib.Path(__file__).resolve().parents[1]
repos={'mapex':'castacks/MapEx','graph':'bairuofei/Graph-Based_SLAM-Aware_Exploration','fael':'SYSU-RoboticsLab/FAEL','falcon':'HKUST-Aerial-Robotics/FALCON','epic':'Robotics-STAR-Lab/EPIC','metricsemantic':'KumarRobotics/kr_3d_active_ms_slam','activesplat':'Li-Yuetao/ActiveSplat','helpme':'ImitationDQN/Imitation-based-DQN-to-avoid-tracking-failures-in-ORBSLAM3-with-released-dataset'}
def f(x):
 name,repo=x;record={'name':name,'repo':repo}
 try:
  res=requests.get('https://github.com/'+repo,timeout=25);p=R/'sources'/name;p.mkdir(exist_ok=True);(p/'root.html').write_text(res.text);record.update(status=res.status_code,bytes=len(res.content))
  for t in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',res.text,re.S):
   try:
    v=json.loads(t)['payload']['codeViewRepoRoute'];record.update(sha=v['refInfo']['currentOid'],branch=v['refInfo']['name'],items=v['tree']['items']);break
   except Exception:pass
  if 'sha' in record:
   u='https://raw.githubusercontent.com/'+repo+'/'+record['sha']+'/README.md';s=requests.get(u,timeout=25);record['readme_status']=s.status_code
   if s.status_code==200:(p/'README.md').write_bytes(s.content)
 except Exception as e:record['error']=str(e)
 return record
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rs=list(ex.map(f,repos.items()))
(R/'audit/repositories.json').write_text(json.dumps(rs,indent=2))
print(json.dumps([{k:v for k,v in x.items() if k!='items'} for x in rs],indent=2))
