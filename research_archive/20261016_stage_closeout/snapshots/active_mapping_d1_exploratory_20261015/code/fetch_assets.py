"""One bounded request per pinned author asset. No model or simulator execution."""
from pathlib import Path
import hashlib,json,time,urllib.parse,requests
R=Path(__file__).resolve().parents[1]
SHA='010e03248ed633e755c84dc4686c6d00e6bb23c8'
paths=['Code/checkpoint_weights/weights_classification/weights_old.h5',
       'Code/image_crop.py','Code/env_create.py','LICENSE']
results=[]
for path in paths:
    row={'path':path,'commit':SHA};start=time.monotonic()
    try:
        url='https://raw.githubusercontent.com/aislabunimi/exploration-aware/'+SHA+'/'+urllib.parse.quote(path)
        response=requests.get(url,stream=True,timeout=(15,60));row['http_status']=response.status_code
        response.raise_for_status()
        dest=R/'sources/author'/path;dest.parent.mkdir(parents=True,exist_ok=True)
        size=0;hasher=hashlib.sha256()
        with dest.open('xb') as stream:
            for block in response.iter_content(1024*1024):
                size+=len(block)
                if size>40*1024*1024:raise ValueError('40MiB per-asset limit')
                stream.write(block);hasher.update(block)
        row.update(bytes=size,sha256=hasher.hexdigest())
    except Exception as error:row['error']=repr(error)
    row['wall_s']=time.monotonic()-start;results.append(row)
    (R/'audit/author_assets.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(row),flush=True)
