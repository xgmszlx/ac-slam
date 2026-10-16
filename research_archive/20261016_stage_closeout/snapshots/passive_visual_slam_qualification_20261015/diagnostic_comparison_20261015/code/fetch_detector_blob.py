import requests,pathlib,time,json,base64,hashlib
N=pathlib.Path(__file__).resolve().parents[1];out=N/'models/mobilenet_iter_73000.caffemodel';partial=out.with_suffix('.partial_raw');out.rename(partial)
s=requests.Session();s.trust_env=False;start=time.monotonic();event={'url':'https://api.github.com/repos/chuanqi305/MobileNet-SSD/git/blobs/253e5012dd6a17666fd7ae16cfa14a6860280ff7','expected_bytes':23306119,'expected_blob_sha1':'253e5012dd6a17666fd7ae16cfa14a6860280ff7','budget_s':60,'prior_raw_failure_retained':str(partial)}
try:
 with s.get(event['url'],headers={'Accept':'application/vnd.github.raw+json'},stream=True,timeout=(10,15)) as r:
  r.raise_for_status();event['content_type']=r.headers.get('content-type');data=bytearray()
  for chunk in r.iter_content(262144):
   data.extend(chunk)
   if len(data)>35000000 or time.monotonic()-start>60:raise RuntimeError('bounded transfer budget exceeded')
 if data[:1]==b'{':data=base64.b64decode(json.loads(data)['content'])
 assert len(data)==23306119
 blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert blob==event['expected_blob_sha1']
 out.write_bytes(data);event.update(success=True,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
except Exception as e:event.update(success=False,error=repr(e))
event['elapsed_s']=time.monotonic()-start;(N/'audit/model_blob_transfer.json').write_text(json.dumps(event,indent=2));print(json.dumps(event,indent=2))
