import pathlib,json,shlex,subprocess,os,hashlib,csv
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4';B=S/'build';lib=N/'build/frame_test_lib/libORB_SLAM3.so'
assert lib.exists();flags=(B/'CMakeFiles/rgbd_tum_headless.dir/flags.make').read_text();f={l.split(' = ')[0]:l.split(' = ')[1] for l in flags.splitlines() if ' = ' in l};obj=N/'build/frame_chain.o';binary=N/'build/frame_chain'
cmd=['/usr/bin/c++','-I'+str(N/'frame_test_source/include')]+shlex.split(f['CXX_DEFINES'])+shlex.split(f['CXX_INCLUDES'])+shlex.split(f['CXX_FLAGS'])+['-UNDEBUG','-c',str(N/'tests/frame_chain.cc'),'-o',str(obj)]
link=shlex.split((B/'CMakeFiles/rgbd_tum_headless.dir/link.txt').read_text());link[link.index('CMakeFiles/rgbd_tum_headless.dir/Examples/RGB-D/rgbd_tum_headless.cc.o')]=str(obj);link[link.index('../lib/libORB_SLAM3.so')]=str(lib);link[link.index('-o')+1]=str(binary)
with (N/'audit/build_frame_chain_test.log').open('w') as log:
 subprocess.run(cmd,cwd=B,stdout=log,stderr=subprocess.STDOUT,check=True);subprocess.run(link,cwd=B,stdout=log,stderr=subprocess.STDOUT,check=True)
env=os.environ.copy();env['LD_LIBRARY_PATH']=str(lib.parent)+':'+str(O/'local/lib')+':'+env.get('LD_LIBRARY_PATH','');d=O/'data/rgbd_dataset_freiburg3_walking_xyz';command=[str(binary),str(d),str(d/'associations.txt'),str(N/'results/frame_chain_test.csv')]
with (N/'audit/frame_chain_test.log').open('w') as log:p=subprocess.run(command,cwd=N,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
r={'exit':p.returncode,'PASS':p.returncode==0,'command':command,'scope':'real Frame and native matcher index tests on current image synthetic rectangle controls','real_person_masks':False,'full_System_Tracking_interface':'NOT_RUN','no_feature_Frame_N0':'tested constructor early return only; downstream full tracking unqualified','GT_online':False}
if p.returncode==0:
 rows=list(csv.DictReader((N/'results/frame_chain_test.csv').open()));r.update(samples=len(rows),all_indices_qualified=all(x['index_tests_PASS']=='1' for x in rows))
(N/'audit/frame_chain_qualification.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2));assert p.returncode==0
