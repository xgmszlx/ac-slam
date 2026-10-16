import sys, json
sys.path.insert(0,__file__.rsplit('/',1)[0])
from fetch_text import fetch, ROOT
from concurrent.futures import ThreadPoolExecutor
REPOS={
 'air':('sair-lab/AirSLAM','d1265771026091db97ee8f7a6d80692f0edd5fef',['README.md','CMakeLists.txt','src/map_builder.cc','src/g2o_optimization/g2o_optimization.cc']),
 'mac':('MAC-VO/MAC-VO','8683b532d6f6e8981f6b1a646fb5f52f02c1ea61',['README.md','requirements.txt','Module/KeypointSelector.py','Module/Covariance/Project2to3.py','Module/Optimization/TwoFramePGO.py']),
 'como':('edexheim/como','56e421a70f8863d9c446d46f52246e4357193346',['README.md','install.sh','config/como.yml']),
}
items=[]
for key,(repo,sha,files) in REPOS.items():
    for f in files: items.append((key+'_'+f.replace('/','_'),'https://raw.githubusercontent.com/'+repo+'/'+sha+'/'+f))
items.extend([('eth3d_alt.html','https://eth3d.ethz.ch/slam_datasets'),('i2_paper.html','https://arxiv.org/html/2407.11347v1')])
with ThreadPoolExecutor(max_workers=4) as ex: result=list(ex.map(fetch,items))
(ROOT/'audit/source_acquisition.json').write_text(json.dumps(result,indent=2))
(ROOT/'protocol/source_versions.json').write_text(json.dumps({k:{'repo':v[0],'sha':v[1],'resolution':'git ls-remote HEAD, current code not certified paper release'} for k,v in REPOS.items()},indent=2))
for x in result: print(json.dumps(x))
