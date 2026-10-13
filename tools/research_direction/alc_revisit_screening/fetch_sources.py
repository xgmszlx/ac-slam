#!/usr/bin/python3
"""Download public paper PDFs only to this screening's ignored cache; no ROS."""
import concurrent.futures
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'results/research_direction/alc_revisit_screening/literature'
CACHE=OUT/'cache'
SOURCES={
 'zhang2026':('https://arxiv.org/pdf/2503.17005v3',None),
 'region2026':('https://arxiv.org/pdf/2504.10416v3',None),
 'lighthouse2023':('https://arxiv.org/pdf/2306.10463v1',None),
 'osm2024':('https://arxiv.org/pdf/2407.17078v1',None),
 'retroactive2026':('https://arxiv.org/pdf/2607.13516v1',None),
 'bai2024':('https://arxiv.org/pdf/2308.16522v2','bai2023.pdf'),
 'yin2024':('https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf','yin2024.pdf'),
 'kim2015':('https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf','kim2015.pdf'),
 'pathak2018':('https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf','pathak2018.pdf'),
 'stachniss2004':('https://www.ipb.uni-bonn.de/papers/stachniss04iros.pdf','stachniss2004.pdf')}
LOCAL=Path('/home/wcqw/ac-slam/results/realizability_pilot/p1_action_selection_exploratory_20261010/literature')


def acquire(item):
    name,(url,old_name)=item
    try:
        path=LOCAL/old_name if old_name and (LOCAL/old_name).is_file() else CACHE/(name+'.pdf')
        if not path.exists():
            request=urllib.request.Request(url,headers={'User-Agent':'AC-SLAM-Offline-Research/1.0'})
            with urllib.request.urlopen(request,timeout=45) as response:data=response.read(32*1024*1024)
            if not data.startswith(b'%PDF'):raise ValueError('Not a PDF')
            with path.open('xb') as stream:stream.write(data)
        text=CACHE/(name+'.txt')
        p=subprocess.run(['pdftotext','-layout',str(path),str(text)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        result={'slug':name,'primary_url':url,'local_pdf':str(path),'text_cache':str(text),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
                'acquired':True,'pdf_pages_by_formfeed':text.read_text(errors='replace').count('\f'),
                'new_external_download':str(path).startswith(str(CACHE))}
    except Exception as exc:result={'slug':name,'primary_url':url,'acquired':False,'error':str(exc)}
    print(json.dumps({k:v for k,v in result.items() if k not in ('text_cache','local_pdf')}),flush=True)
    return result


if __name__=='__main__':
    CACHE.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(acquire,SOURCES.items()))
    (OUT/'acquisition_manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
