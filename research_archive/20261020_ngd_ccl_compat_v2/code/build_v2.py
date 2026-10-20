from pathlib import Path
import json,hashlib,subprocess,shutil,difflib,os,shlex
D=Path(__file__).resolve().parents[1];V=Path('/home/wcqw/ngd_ccl_compat_20261020');O=Path('/home/wcqw/ngd_native_recovery_20261020');P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');E1=P.parent/'ngd_ccl_compat_20261020';E=P.parent/'ngd_ccl_compat_v2_20261020';S=E/'NGD-SLAM';B=P/'ngd-build';H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not S.exists() and not (D/'protocol/protection_before.json').exists()
a=json.loads((O/'audit/source_acceptance.json').read_text())
files={}
for root in [V,O]:
 for p in root.rglob('*'):
  if p.is_file():files[str(p)]=H(p)
for root in [E1/'NGD-SLAM',P/'NGD-SLAM']:
 for rel in a['files']:files[str(root/rel)]=H(root/rel)
for p in [E1/'lib/libORB_SLAM3.so',E1/'rgbd_tum_headless',E1/'YOLO_compat.o',P/'NGD-SLAM/lib/libORB_SLAM3.so',P/'rgbd_tum_headless']:
 files[str(p)]=H(p)
G=lambda x:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+x,text=True)
(D/'protocol/protection_before.json').write_text(json.dumps({'files':files,'head':G(['rev-parse','HEAD']),'status':G(['status','--porcelain']),'diff_sha256':hashlib.sha256(G(['diff']).encode()).hexdigest()},indent=2))
plan={'label':'NGD-M0-compat-v2','parent_commit':'40035951ba461fc782fc47db5b61d4675c80e6f0','source_commit':'a93a14c4019efc7a209be5fbf9fefa46f5d1d90f','only_new_change':'src/Tracking.cc CreateMaskFromClusters explicit CCL_SAUF, connectivity4/CV_32S; prior YOLO fix retained','untouched_risk':'pointsDepth may be empty before median access; do not fix preemptively','short_frames':12,'full_frames':827,'full_budget':1,'full_gate':'short exit0 and exactly12 completed TrackRGBD calls','threads':1,'new_fault_action':'one exact GDB prefix replay; stop without other source edits','repro_cases':['zero10','zero480','diag10','rects','tie','edge'],'algorithms':['default','sauf'],'threads_semantic':[1,4]}
(D/'protocol/plan.json').write_text(json.dumps(plan,indent=2))
for rel in a['files']:
 src=E1/'NGD-SLAM'/rel;dst=S/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
p=S/'src/Tracking.cc';s=p.read_text();needle='cv::connectedComponentsWithStats(localMask, labels, stats, centroids, 4, CV_32S)';assert s.count(needle)==1;t=s.replace(needle,needle[:-1]+', cv::CCL_SAUF)');p.write_text(t)
for rel in ['src/Tracking.cc','src/YOLO.cc']:
 old=(P/'NGD-SLAM'/rel).read_text();new=(S/rel).read_text();(D/'audit'/(Path(rel).stem+'_sauf.patch')).write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
calls=[]
for p in S.rglob('*'):
 if p.suffix in ['.cc','.cpp','.h','.hpp']:
  for i,l in enumerate(p.read_text(errors='replace').splitlines(),1):
   if 'connectedComponentsWithStats' in l:calls.append({'file':str(p.relative_to(S)),'line':i,'text':l.strip()})
assert len(calls)==2 and all('cv::CCL_SAUF' in x['text'] for x in calls)
(D/'audit/call_sites.json').write_text(json.dumps(calls,indent=2))
f={}
for l in (B/'CMakeFiles/ORB_SLAM3.dir/flags.make').read_text().splitlines():
 if ' = ' in l:k,v=l.split(' = ',1);f[k]=shlex.split(v)
c=['/usr/bin/c++']+f['CXX_DEFINES']+f['CXX_INCLUDES']+f['CXX_FLAGS']+['-c',str(S/'src/Tracking.cc'),'-o',str(E/'Tracking_compat_v2.o')]
l=shlex.split((B/'CMakeFiles/ORB_SLAM3.dir/link.txt').read_text());l[l.index('-o')+1]=str(E/'lib/libORB_SLAM3.so');l[l.index('CMakeFiles/ORB_SLAM3.dir/src/YOLO.cc.o')]=str(E1/'YOLO_compat.o');l[l.index('CMakeFiles/ORB_SLAM3.dir/src/Tracking.cc.o')]=str(E/'Tracking_compat_v2.o');l=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in l]
head=json.loads((O/'audit/headless_build.json').read_text())['link'];head[head.index('-o')+1]=str(E/'rgbd_tum_headless');head=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in head]
env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['TMPDIR']=str(E/'tmp');env.pop('LD_LIBRARY_PATH',None)
(D/'protocol/build_frozen.json').write_text(json.dumps({'commands':[c,l,head],'tracking_source_sha256':H(S/'src/Tracking.cc'),'YOLO_reused_object_sha256':H(E1/'YOLO_compat.o')},indent=2))
with (D/'audit/build.log').open('w') as log:
 for cmd in [c,l,head]:subprocess.run(cmd,cwd=B,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
changed=[p for p,r in a['files'].items() if H(S/p)!=r['sha256']];assert sorted(changed)==['src/Tracking.cc','src/YOLO.cc']
ldd=subprocess.check_output(['/usr/bin/ldd',str(E/'rgbd_tum_headless')],env=env,text=True);assert str(E/'lib/libORB_SLAM3.so') in ldd and '.so.4.2' not in ldd
(D/'audit/build.json').write_text(json.dumps({'changed_author_files':changed,'recompiled_TU':['src/Tracking.cc'],'ldd':ldd,'hashes':{str(p):H(p) for p in [E/'lib/libORB_SLAM3.so',E/'rgbd_tum_headless',S/'src/Tracking.cc',S/'src/YOLO.cc']}},indent=2))
print('v2 build PASS; only Tracking recompiled; YOLO-compatible object reused')
