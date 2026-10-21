from pathlib import Path
import shlex,subprocess,json,os,sys,shutil,difflib
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_region_prototype_20261021');S=E/'NGD-SLAM';P=E.parent/'ngd_native_recovery_20261020';B=P/'ngd-build';V=E.parent/'ngd_ccl_compat_v2_20261020'
env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['TMPDIR']=str(E/'tmp');env.pop('LD_LIBRARY_PATH',None)
f={}
for line in (B/'CMakeFiles/ORB_SLAM3.dir/flags.make').read_text().splitlines():
 if ' = ' in line:k,v=line.split(' = ',1);f[k]=shlex.split(v)
flags=f['CXX_DEFINES']+['-I'+str(S/'include')]+f['CXX_INCLUDES']+f['CXX_FLAGS'];commands=[]
def run(cmd,name,cwd=B):
 commands.append(cmd)
 with (D/'audit'/name).open('w') as log:subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
for name,dest in [('RegionExpansion.h',S/'include/RegionExpansion.h'),('RegionExpansion.cc',S/'src/RegionExpansion.cc')]:shutil.copy2(D/'code'/name,dest)
run(['/usr/bin/c++']+flags+['-c',str(S/'src/RegionExpansion.cc'),'-o',str(E/'RegionExpansion.o')],'compile_region.log')
if sys.argv[1]=='test':
 run(['/usr/bin/c++']+flags+['-c',str(D/'code/region_tests.cc'),'-o',str(E/'region_tests.o')],'compile_tests.log')
 cmd=json.loads(Path('/home/wcqw/ngd_native_recovery_20261020/audit/headless_build.json').read_text())['link']
 oldobj=next(x for x in cmd if x.endswith('headless_entry.o'));cmd[cmd.index(oldobj)]=str(E/'region_tests.o');cmd.insert(cmd.index('-o'),str(E/'RegionExpansion.o'));cmd[cmd.index('-o')+1]=str(E/'region_tests');cmd=[x.replace(str(P/'NGD-SLAM/lib'),str(V/'lib')) for x in cmd]
 run(cmd,'link_tests.log');(D/'audit/test_build_commands.json').write_text(json.dumps(commands,indent=2));print('unit binary built');sys.exit(0)
for name in ([] if sys.argv[1]=='relink' else ['Tracking.cc','Frame.cc','ORBmatcher.cc','Optimizer.cc']):
 run(['/usr/bin/c++']+flags+['-c',str(S/'src'/name),'-o',str(E/(name+'.o'))],'compile_'+name+'.log')
l=shlex.split((B/'CMakeFiles/ORB_SLAM3.dir/link.txt').read_text());l[l.index('-o')+1]=str(E/'lib/libORB_SLAM3.so')
for name in ['Tracking.cc','Frame.cc','ORBmatcher.cc','Optimizer.cc']:l[l.index('CMakeFiles/ORB_SLAM3.dir/src/'+name+'.o')]=str(E/(name+'.o'))
l[l.index('CMakeFiles/ORB_SLAM3.dir/src/YOLO.cc.o')]=str(P.parent/'ngd_ccl_compat_20261020/YOLO_compat.o');l.insert(l.index('-L'+str(P/'NGD-SLAM/Thirdparty/g2o/lib')),str(E/'RegionExpansion.o'));l=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in l];run(l,'link_core.log')
head=json.loads(Path('/home/wcqw/ngd_native_recovery_20261020/audit/headless_build.json').read_text());compile=head['compile'];src=next(x for x in compile if x.endswith('.cc'));obj=compile[compile.index('-o')+1];compile[compile.index(src)]=str(D/'code/rgbd_region.cc');compile[compile.index('-o')+1]=str(E/'rgbd_region.o');compile.insert(1,'-I'+str(S/'include'));run(compile,'compile_entry.log')
l=head['link'];l[l.index(obj)]=str(E/'rgbd_region.o');l[l.index('-o')+1]=str(E/'rgbd_region');l=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in l];run(l,'link_entry.log')
(D/'audit/build_commands.json').write_text(json.dumps(commands,indent=2));print('COMMON_BINARY_BUILT')
