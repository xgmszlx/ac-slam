from pathlib import Path
import shlex,subprocess,os,json,tarfile
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');B=E/'ngd-build';f={}
for l in (B/'CMakeFiles/rgbd_tum.dir/flags.make').read_text().splitlines():
 if ' = ' in l:
  k,v=l.split(' = ',1);f[k]=shlex.split(v)
env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['TMPDIR']=str(E/'tmp');env.pop('LD_LIBRARY_PATH',None)
c=['/usr/bin/c++']+f['CXX_DEFINES']+f['CXX_INCLUDES']+f['CXX_FLAGS']+['-c',str(D/'code/rgbd_tum_headless.cc'),'-o',str(E/'headless_entry.o')]
l=shlex.split((B/'CMakeFiles/rgbd_tum.dir/link.txt').read_text());l[l.index('-o')+1]=str(E/'rgbd_tum_headless');obj='CMakeFiles/rgbd_tum.dir/Examples/RGB-D/rgbd_tum.cc.o';assert obj in l;l[l.index(obj)]=str(E/'headless_entry.o')
with (D/'audit/headless_build.log').open('w') as out:
 for cmd in [c,l]:subprocess.run(cmd,cwd=B,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
v=E/'NGD-SLAM/Vocabulary'
with tarfile.open(v/'ORBvoc.txt.tar.gz') as t:
 assert all(m.name=='ORBvoc.txt' for m in t.getmembers());t.extractall(v)
(D/'audit/headless_build.json').write_text(json.dumps({'compile':c,'link':l,'entry_only_change':'viewer bool false; exact author example flags and shared NGD library'},indent=2));print('Author native entry and headless entry both linked; vocabulary extracted')
