"""Metadata and source checks only. Never imports or executes author SLAM code."""
import ast, hashlib, json, pathlib, platform, shutil, subprocess
ROOT=pathlib.Path('/home/wcqw/passive_visual_slam_v2_v3_screen_20261015')
OLD=pathlib.Path('/home/wcqw/passive_visual_slam_qualification_20261015')
def cmd(args):
    r=subprocess.run(args,capture_output=True,text=True,timeout=15)
    return dict(command=args,exit=r.returncode,stdout=r.stdout,stderr=r.stderr)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
out={'disk':dict(zip(['total','used','free'],shutil.disk_usage('/'))),'checks':[]}
for args in [ ['/usr/bin/python3','-c','import cv2,sys;print(sys.version);print(cv2.__version__)'],
 ['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader'],
 ['/usr/local/cuda-11.8/bin/nvcc','--version'],['free','-b'],
 ['ldconfig','-p']]:
    r=cmd(args)
    if args[0]=='ldconfig':r['stdout']='\n'.join(x for x in r['stdout'].splitlines() if any(t in x for t in ['nvinfer','nvonnx','ceres','g2o','opencv_core']))
    out['checks'].append(r)
out['torch_default_python']=cmd(['python3','-c','import importlib.util,sys; print(sys.version); print(importlib.util.find_spec("torch"))'])
out['author_ast']={}
for p in (ROOT/'sources').glob('*.py'):
    try:ast.parse(p.read_text());out['author_ast'][p.name]='PASS_SYNTAX_ONLY'
    except Exception as e:out['author_ast'][p.name]=str(e)
out['existing_orb']={}
for p in [OLD/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4/lib/libORB_SLAM3.so',OLD/'diagnostic_comparison_20261015/build/rgbd_diagnostic']:
    out['existing_orb'][str(p)]=dict(exists=p.is_file(),sha256=sha(p) if p.is_file() else None)
out['scope']='STATIC_FEASIBILITY_ONLY; no build, no dataset/model payload, no SLAM run'
(ROOT/'audit/environment_and_static.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in ['checks','torch_default_python']},indent=2))
