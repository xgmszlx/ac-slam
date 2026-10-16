import pathlib,subprocess,shlex,json,hashlib,time
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4';B=S/'build';src=N/'frame_test_source';out=N/'build/frame_test_lib';out.mkdir(exist_ok=True)
flags=(B/'CMakeFiles/ORB_SLAM3.dir/flags.make').read_text();f={l.split(' = ')[0]:l.split(' = ')[1] for l in flags.splitlines() if ' = ' in l}
obj=out/'Frame.cc.o';cmd=['/usr/bin/c++','-I'+str(src/'include')]+shlex.split(f['CXX_DEFINES'])+shlex.split(f['CXX_INCLUDES'])+shlex.split(f['CXX_FLAGS'])+['-c',str(src/'src/Frame.cc'),'-o',str(obj)]
link=shlex.split((B/'CMakeFiles/ORB_SLAM3.dir/link.txt').read_text());native_object='CMakeFiles/ORB_SLAM3.dir/src/Frame.cc.o';assert link.count(native_object)==1;link[link.index(native_object)]=str(obj);link[link.index('-o')+1]=str(out/'libORB_SLAM3.so')
record={'scope':'compile Frame.cc frontend only; link read-only original object files for every other component, including optimizer, System and Tracking','compile':cmd,'link':link,'original_backend_objects_sha256':{str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (B/'CMakeFiles/ORB_SLAM3.dir/src').rglob('*.o') if p.name!='Frame.cc.o'},'Frame_source_same_as_prior_draft':True}
(N/'protocol/frame_test_build_frozen.json').write_text(json.dumps(record,indent=2))
start=time.monotonic()
with (N/'audit/build_frame_test_lib.log').open('w') as log:
 subprocess.run(cmd,cwd=B,stdout=log,stderr=subprocess.STDOUT,check=True);subprocess.run(link,cwd=B,stdout=log,stderr=subprocess.STDOUT,check=True)
(N/'audit/frame_test_library.json').write_text(json.dumps({'elapsed_s':time.monotonic()-start,'sha256':hashlib.sha256((out/'libORB_SLAM3.so').read_bytes()).hexdigest(),'not_a_P2_ready_System_or_Tracking_interface':True,'backend_objects_recompiled':0},indent=2));print('Frame-only test library built')
