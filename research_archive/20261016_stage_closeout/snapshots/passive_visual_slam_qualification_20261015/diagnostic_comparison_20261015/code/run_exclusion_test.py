import pathlib,shlex,subprocess,json,os
N=pathlib.Path(__file__).resolve().parents[1];S=N.parent/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4';b=S/'build'
flags=(b/'CMakeFiles/rgbd_tum_headless.dir/flags.make').read_text();f={l.split(' = ')[0]:l.split(' = ')[1] for l in flags.splitlines() if ' = ' in l}
# Assertions stay active in unit test, irrespective of original Release -DNDEBUG.
cmd=['/usr/bin/c++','-I'+str(N/'masked_source/include')]+shlex.split(f['CXX_DEFINES'])+shlex.split(f['CXX_INCLUDES'])+shlex.split(f['CXX_FLAGS'])+['-UNDEBUG','-c',str(N/'tests/test_exclusion.cc'),'-o',str(N/'build/test_exclusion.o')]
link=shlex.split((b/'CMakeFiles/rgbd_tum_headless.dir/link.txt').read_text());link[link.index('CMakeFiles/rgbd_tum_headless.dir/Examples/RGB-D/rgbd_tum_headless.cc.o')]=str(N/'build/test_exclusion.o');link[link.index('-o')+1]=str(N/'build/test_exclusion')
with (N/'audit/exclusion_test_build.log').open('w') as log:
 subprocess.run(cmd,cwd=b,stdout=log,stderr=subprocess.STDOUT,check=True);subprocess.run(link,cwd=b,stdout=log,stderr=subprocess.STDOUT,check=True)
d=N.parent/'data/rgbd_dataset_freiburg3_walking_xyz';im=(d/'associations.txt').read_text().splitlines()[0].split()[1];env=os.environ.copy();env['LD_LIBRARY_PATH']=str(S/'lib')+':'+str(N.parent/'local/lib')+':'+env.get('LD_LIBRARY_PATH','')
r=subprocess.run([str(N/'build/test_exclusion'),str(d/im)],cwd=N,env=env,text=True,capture_output=True);(N/'audit/exclusion_unit_test.log').write_text(r.stdout+r.stderr);assert r.returncode==0
result=json.loads(r.stdout);(N/'audit/exclusion_helper_test.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
(N/'audit/mask_filter_tests.json').write_text(json.dumps({'PASS':False,'software_helper_tests':'PASS','full_Frame_depth_map_integration':'NOT_RUN','mask_source_quality':'MASK_NOT_QUALIFIED','P2_runs_authorized_after_tests':False},indent=2))
