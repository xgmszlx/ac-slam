"""Bounded single attempt official transport. Failed partial files are retained."""
import requests,time,json,hashlib,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
url,name,budget=sys.argv[1],sys.argv[2],float(sys.argv[3])
out=root/name
out.parent.mkdir(exist_ok=True,parents=True)
event={'url':url,'path':str(out),'start':time.time(),'budget_s':budget,'attempt':1}
try:
    with requests.get(url,stream=True,timeout=(10,20),verify='/etc/ssl/certs/ca-certificates.crt') as r:
        event.update(http=r.status_code,final_url=r.url,headers={k:v for k,v in r.headers.items() if k.lower() in ['content-length','content-type','last-modified','etag']})
        r.raise_for_status()
        n=0; h=hashlib.sha256()
        with out.open('xb') as f:
            for b in r.iter_content(65536):
                if time.time()-event['start']>budget:raise TimeoutError('total transfer budget exceeded')
                f.write(b);h.update(b);n+=len(b)
        expected=r.headers.get('Content-Length')
        if expected and n!=int(expected):raise ValueError('Content-Length mismatch')
        event.update(status='COMPLETE',bytes=n,sha256=h.hexdigest())
except Exception as e:
    event.update(status='FAILED',error=repr(e),bytes=out.stat().st_size if out.exists() else 0)
event['duration_s']=time.time()-event['start']
with (root/'audit/downloads.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
print(json.dumps(event),flush=True)
sys.exit(0 if event['status']=='COMPLETE' else 2)
