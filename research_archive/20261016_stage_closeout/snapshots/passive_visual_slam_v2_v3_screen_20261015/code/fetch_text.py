"""Bounded official text/metadata acquisition; no model or dataset payloads."""
import concurrent.futures, hashlib, json, pathlib, requests, time
ROOT=pathlib.Path('/home/wcqw/passive_visual_slam_v2_v3_screen_20261015')
URLS={
 'air_paper.html':'https://arxiv.org/html/2408.03520v4',
 'mac_paper.html':'https://arxiv.org/html/2409.09479v2',
 'como_paper.html':'https://arxiv.org/html/2404.03531v2',
 'four_seasons.html':'https://link.springer.com/article/10.1007/s11263-024-02230-4',
 'eth3d_datasets.html':'https://www.eth3d.net/slam_datasets',
 'eth3d_documentation.html':'https://www.eth3d.net/slam_documentation',
}
REPOS=['sair-lab/AirSLAM','MAC-VO/MAC-VO','edexheim/como']
for repo in REPOS:
    URLS[repo.replace('/','_')+'_commit.json']='https://api.github.com/repos/'+repo+'/commits?per_page=1'
def fetch(item):
    name,url=item; t=time.monotonic(); entry={'name':name,'url':url}
    try:
        with requests.get(url,timeout=(8,18),stream=True) as r:
            entry.update(status=r.status_code,final_url=r.url)
            r.raise_for_status(); b=b''
            for c in r.iter_content(32768):
                b+=c
                if len(b)>1800000: raise RuntimeError('text cap exceeded')
                if time.monotonic()-t>25: raise TimeoutError('total time cap')
            (ROOT/'sources'/name).write_bytes(b)
            entry.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    except Exception as e: entry['error']=str(e)
    entry['seconds']=time.monotonic()-t
    return entry
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: entries=list(ex.map(fetch,URLS.items()))
    (ROOT/'audit/acquisition.json').write_text(json.dumps(entries,indent=2))
    for e in entries: print(json.dumps(e))
