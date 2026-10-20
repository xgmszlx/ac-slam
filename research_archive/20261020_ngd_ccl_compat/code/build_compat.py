from pathlib import Path
import json,hashlib,subprocess,shutil,difflib,os,shlex
D=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/ngd_native_recovery_20261020');P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020');S=E/'NGD-SLAM';B=P/'ngd-build';H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not S.exists()
a=json.loads((O/'audit/source_acceptance.json').read_text())
for p,r in a['files'].items():
 old=P/'NGD-SLAM'/p;assert H(old)==r['sha256'];q=S/p;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,q)
p=S/'src/YOLO.cc';s=p.read_text();needle='cv::connectedComponentsWithStats(localMask, labels, stats, centroids, 4, CV_32S)';assert s.count(needle)==1;t=s.replace(needle,needle[:-1]+', cv::CCL_SAUF)');p.write_text(t)
(D/'audit/yolo_sauf.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),t.splitlines(True),fromfile='a/src/YOLO.cc',tofile='b/src/YOLO.cc')))
f={}
for l in (B/'CMakeFiles/ORB_SLAM3.dir/flags.make').read_text().splitlines():
 if ' = ' in l:k,v=l.split(' = ',1);f[k]=shlex.split(v)
# Compile only YOLO; copy headers are identical. All other object files remain read-only.
c=['/usr/bin/c++']+f['CXX_DEFINES']+f['CXX_INCLUDES']+f['CXX_FLAGS']+['-c',str(p),'-o',str(E/'YOLO_compat.o')]
l=shlex.split((B/'CMakeFiles/ORB_SLAM3.dir/link.txt').read_text());l[l.index('-o')+1]=str(E/'lib/libORB_SLAM3.so');l[l.index('CMakeFiles/ORB_SLAM3.dir/src/YOLO.cc.o')]=str(E/'YOLO_compat.o');l=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in l]
head=json.loads((O/'audit/headless_build.json').read_text())['link'];head[head.index('-o')+1]=str(E/'rgbd_tum_headless');head=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in head]
# Existing headless example object reused verbatim; no entry or logging changes.
env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['TMPDIR']=str(E/'tmp');env.pop('LD_LIBRARY_PATH',None)
with (D/'audit/build_compat.log').open('w') as log:
 for cmd in [c,l,head]:subprocess.run(cmd,cwd=B,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
changed=[p for p,r in a['files'].items() if H(S/p)!=r['sha256']];assert changed==['src/YOLO.cc'],changed
ldd=subprocess.check_output(['/usr/bin/ldd',str(E/'rgbd_tum_headless')],env=env).decode();assert str(E/'lib/libORB_SLAM3.so') in ldd and '.so.4.2' not in ldd
(D/'audit/compat_build.json').write_text(json.dumps({'commands':[c,l,head],'changed_author_files':changed,'changed_expression':needle+' -> '+needle[:-1]+', cv::CCL_SAUF)','recompiled_estimator_translation_units':['src/YOLO.cc'],'reused_other_objects':'all prior original core objects and original headless entry object','ldd':ldd,'hashes':{str(p):H(p) for p in [E/'lib/libORB_SLAM3.so',E/'rgbd_tum_headless',S/'src/YOLO.cc']}},indent=2))
print('Compatibility build PASS; only YOLO TU rebuilt; one changed author expression')
