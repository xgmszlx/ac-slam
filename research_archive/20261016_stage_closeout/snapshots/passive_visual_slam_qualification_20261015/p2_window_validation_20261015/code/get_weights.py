import pathlib,requests,time,json,hashlib,concurrent.futures as cf,os
N=pathlib.Path(__file__).resolve().parents[1];D=N.parent/'diagnostic_comparison_20261015';size=23306119;expected='253e5012dd6a17666fd7ae16cfa14a6860280ff7';start=time.monotonic();deadline=start+300;events=[]
if (N/'audit/weights_qualification.json').exists(): raise SystemExit('Acquisition result already frozen; no automatic retry.')
def event(x):
 x['elapsed_s']=time.monotonic()-start;events.append(x)
 with (N/'audit/download_events.jsonl').open('a') as f:f.write(json.dumps(x)+'\n')
 print(json.dumps(x),flush=True)
def check(p):
 b=p.read_bytes();sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();return len(b)==size and sha==expected
proto=(D/'audit/detector_source/deploy.prototxt').read_bytes();assert hashlib.sha1(b'blob '+str(len(proto)).encode()+b'\0'+proto).hexdigest()=='88021a94bca5c22753a23664d388d4922b2186bb';(N/'models/deploy.prototxt').write_bytes(proto)
existing=[]
for p in (D/'models').glob('*'):
 existing.append({'file':str(p),'bytes':p.stat().st_size,'complete_valid':check(p)})
 if check(p):(N/'models/mobilenet_iter_73000.caffemodel').write_bytes(p.read_bytes())
(N/'audit/existing_weights.json').write_text(json.dumps(existing,indent=2))
raw='https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/bb17b6c3eef36d80be441ae8e5339be66e8e3b7a/mobilenet_iter_73000.caffemodel'
api='https://api.github.com/repos/chuanqi305/MobileNet-SSD/git/blobs/'+expected
google='https://drive.google.com/uc?export=download&id=0B3gersZ2cHIxRm5PMWRoTkdHdHc&resourcekey=0-1Lpfs4EvGDeCQz12AF64hQ'
def read(r,p,limit,stop):
 count=0
 with p.open('xb') as f:
  for b in r.iter_content(16384):
   if time.monotonic()>stop:raise TimeoutError('frozen wall budget reached')
   count+=len(b)
   if count>limit:raise ValueError('unexpected payload size')
   f.write(b)
 return count
for route,url,proxy in [(1,raw,False),(2,api,True),(3,google,False)]:
 if (N/'models/mobilenet_iter_73000.caffemodel').exists():break
 if time.monotonic()>deadline:break
 p=N/'models'/('route'+str(route)+'.partial');stop=min(deadline,time.monotonic()+95);session=requests.Session();session.trust_env=proxy
 try:
  headers={'Accept-Encoding':'identity','User-Agent':'SLAM-fixed-artifact-reproduction'}
  if route==1:headers['Range']='bytes=0-262143'
  if route==2:headers['Accept']='application/vnd.github.raw+json'
  with session.get(url,headers=headers,stream=True,timeout=(10,15)) as r:
   r.raise_for_status();event({'route':route,'event':'headers','status':r.status_code,'type':r.headers.get('Content-Type'),'length':r.headers.get('Content-Length'),'range':r.headers.get('Content-Range'),'final_url':r.url})
   if route==1 and r.status_code==206:
    assert r.headers.get('Content-Range')=='bytes 0-262143/23306119'
    n=read(r,p,262144,stop);assert n==262144
    fd=os.open(p,os.O_RDWR);os.ftruncate(fd,size)
    # Each remaining distinct range is requested once; retain partial output on any failure.
    edges=[262144+((size-262144)*i)//7 for i in range(8)]
    def part(i):
     lo,hi=edges[i],edges[i+1]-1;s=requests.Session();s.trust_env=False;pos=lo
     with s.get(raw,headers={'Range':f'bytes={lo}-{hi}','Accept-Encoding':'identity'},stream=True,timeout=(10,15)) as q:
      q.raise_for_status();assert q.status_code==206 and q.headers.get('Content-Range')==f'bytes {lo}-{hi}/{size}'
      for b in q.iter_content(16384):
       if time.monotonic()>stop:raise TimeoutError('range budget reached')
       if pos+len(b)>hi+1:raise ValueError('range overflow')
       assert os.pwrite(fd,b,pos)==len(b);pos+=len(b)
      assert pos==hi+1
     return {'route':route,'range_completed':[lo,hi]}
    try:
     with cf.ThreadPoolExecutor(max_workers=7) as pool:
      for x in pool.map(part,range(7)):event(x)
    finally:os.close(fd)
   else:
    if 'text/html' in r.headers.get('Content-Type',''):raise ValueError('HTML rather than model; no unbounded confirmation/download retries')
    read(r,p,size+1024,stop)
  if not check(p):raise ValueError('full expected Git blob SHA1 verification failed')
  p.rename(N/'models/mobilenet_iter_73000.caffemodel');event({'route':route,'event':'VERIFIED','bytes':size,'git_blob_sha1':expected})
 except Exception as e:event({'route':route,'event':'FAILED','error':repr(e),'partial_bytes':p.stat().st_size if p.exists() else 0})
 finally:session.close()
valid=(N/'models/mobilenet_iter_73000.caffemodel').exists();result={'PASS':valid,'mask_model_source_qualified':valid,'commit':'bb17b6c3eef36d80be441ae8e5339be66e8e3b7a','git_blob_sha1':expected,'expected_bytes':size,'elapsed_s':time.monotonic()-start,'events':events,'no_more_acquisition_attempts':True}
if valid:result['sha256']=hashlib.sha256((N/'models/mobilenet_iter_73000.caffemodel').read_bytes()).hexdigest()
(N/'audit/weights_qualification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
